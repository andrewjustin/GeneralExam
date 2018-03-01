"""Methods for handling atmospheric fronts.

A front may be represented as either a polyline or a set of grid points.
"""

import numpy
import pandas
import cv2
import shapely.geometry
from scipy.ndimage.morphology import binary_dilation
from scipy.ndimage.morphology import binary_closing
from scipy.ndimage import generate_binary_structure
from skimage.measure import label as label_image
from gewittergefahr.gg_utils import grids
from gewittergefahr.gg_utils import nwp_model_utils
from gewittergefahr.gg_utils import polygons
from gewittergefahr.gg_utils import time_conversion
from gewittergefahr.gg_utils import error_checking

TOLERANCE_DEG = 1e-3
TIME_FORMAT_FOR_LOG_MESSAGES = '%Y-%m-%d-%H'

STRUCTURE_MATRIX_FOR_BINARY_CLOSING = numpy.ones((3, 3))

FRONT_TYPE_COLUMN = 'front_type'
TIME_COLUMN = 'unix_time_sec'
LATITUDES_COLUMN = 'latitudes_deg'
LONGITUDES_COLUMN = 'longitudes_deg'

WARM_FRONT_ROW_INDICES_COLUMN = 'warm_front_row_indices'
WARM_FRONT_COLUMN_INDICES_COLUMN = 'warm_front_column_indices'
COLD_FRONT_ROW_INDICES_COLUMN = 'cold_front_row_indices'
COLD_FRONT_COLUMN_INDICES_COLUMN = 'cold_front_column_indices'

ROW_INDICES_BY_REGION_KEY = 'row_indices_by_region'
COLUMN_INDICES_BY_REGION_KEY = 'column_indices_by_region'
FRONT_TYPE_BY_REGION_KEY = 'front_type_by_region'

NO_FRONT_INTEGER_ID = 0
WARM_FRONT_INTEGER_ID = 1
COLD_FRONT_INTEGER_ID = 2
ANY_FRONT_INTEGER_ID = 1

WARM_FRONT_STRING_ID = 'warm'
COLD_FRONT_STRING_ID = 'cold'
VALID_STRING_IDS = [WARM_FRONT_STRING_ID, COLD_FRONT_STRING_ID]


def _check_polyline(vertex_x_coords_metres, vertex_y_coords_metres):
    """Checks polyline for errors.

    V = number of vertices

    :param vertex_x_coords_metres: length-V numpy array with x-coordinates of
        vertices.
    :param vertex_y_coords_metres: length-V numpy array with y-coordinates of
        vertices.
    """

    error_checking.assert_is_numpy_array_without_nan(vertex_x_coords_metres)
    error_checking.assert_is_numpy_array(
        vertex_x_coords_metres, num_dimensions=1)
    num_vertices = len(vertex_x_coords_metres)

    error_checking.assert_is_numpy_array_without_nan(vertex_y_coords_metres)
    error_checking.assert_is_numpy_array(
        vertex_y_coords_metres, exact_dimensions=numpy.array([num_vertices]))


def _vertex_arrays_to_list(vertex_x_coords_metres, vertex_y_coords_metres):
    """Converts set of vertices from two arrays to one list.

    V = number of vertices

    :param vertex_x_coords_metres: length-V numpy array with x-coordinates of
        vertices.
    :param vertex_y_coords_metres: length-V numpy array with y-coordinates of
        vertices.
    :return: vertex_list_xy_metres: length-V list, where each element is an
        (x, y) tuple.
    """

    _check_polyline(vertex_x_coords_metres=vertex_x_coords_metres,
                    vertex_y_coords_metres=vertex_y_coords_metres)

    num_vertices = len(vertex_x_coords_metres)
    vertex_list_xy_metres = []
    for i in range(num_vertices):
        vertex_list_xy_metres.append(
            (vertex_x_coords_metres[i], vertex_y_coords_metres[i]))

    return vertex_list_xy_metres


def _polyline_from_vertex_arrays_to_linestring(
        vertex_x_coords_metres, vertex_y_coords_metres):
    """Converts polyline from vertex arrays to `shapely.geometry.LineString`.

    V = number of vertices

    :param vertex_x_coords_metres: length-V numpy array with x-coordinates of
        vertices.
    :param vertex_y_coords_metres: length-V numpy array with y-coordinates of
        vertices.
    :return: linestring_object_xy_metres: Instance of
        `shapely.geometry.LineString`, with vertex coordinates in metres.
    :raises: ValueError: if resulting LineString object is invalid.
    """

    vertex_list_xy_metres = _vertex_arrays_to_list(
        vertex_x_coords_metres=vertex_x_coords_metres,
        vertex_y_coords_metres=vertex_y_coords_metres)

    linestring_object_xy_metres = shapely.geometry.LineString(
        vertex_list_xy_metres)
    if not linestring_object_xy_metres.is_valid:
        raise ValueError('Resulting LineString object is invalid.')

    return linestring_object_xy_metres


def _grid_cell_to_polygon(
        grid_point_x_metres, grid_point_y_metres, x_spacing_metres,
        y_spacing_metres):
    """Converts a grid cell to a polygon.

    This method assumes that the grid is regular in x-y coordinates, not in lat-
    long coordinates.

    :param grid_point_x_metres: x-coordinate of center point ("grid point").
    :param grid_point_y_metres: y-coordinate of center point ("grid point").
    :param x_spacing_metres: Spacing between adjacent grid points in
        x-direction.
    :param y_spacing_metres: Spacing between adjacent grid points in
        y-direction.
    :return: grid_cell_edge_polygon_xy_metres: Instance of
        `shapely.geometry.Polygon`, where each vertex is a corner of the grid
        cell.  Coordinates are in metres.
    """

    x_min_metres = grid_point_x_metres - x_spacing_metres / 2
    x_max_metres = grid_point_x_metres + x_spacing_metres / 2
    y_min_metres = grid_point_y_metres - y_spacing_metres / 2
    y_max_metres = grid_point_y_metres + y_spacing_metres / 2

    vertex_x_coords_metres = numpy.array(
        [x_min_metres, x_max_metres, x_max_metres, x_min_metres, x_min_metres])
    vertex_y_coords_metres = numpy.array(
        [y_min_metres, y_min_metres, y_max_metres, y_max_metres, y_min_metres])

    return polygons.vertex_arrays_to_polygon_object(
        exterior_x_coords=vertex_x_coords_metres,
        exterior_y_coords=vertex_y_coords_metres)


def _polyline_to_grid_points(
        polyline_x_coords_metres, polyline_y_coords_metres,
        grid_point_x_coords_metres, grid_point_y_coords_metres):
    """Converts a polyline to a set of grid points.

    P = number of vertices in polyline
    M = number of grid rows (unique grid-point y-coordinates)
    N = number of grid columns (unique grid-point x-coordinates)
    Q = number of grid points in polyline

    This method assumes that `grid_point_x_coords_metres` and
    `grid_point_y_coords_metres` are sorted in ascending order and equally
    spaced.  In other words, the grid must be *regular* in x-y.

    :param polyline_x_coords_metres: length-P numpy array with x-coordinates in
        polyline.
    :param polyline_y_coords_metres: length-P numpy array with y-coordinates in
        polyline.
    :param grid_point_x_coords_metres: length-N numpy array with unique
        x-coordinates of grid points.
    :param grid_point_y_coords_metres: length-M numpy array with unique
        y-coordinates of grid points.
    :return: rows_in_polyline: length-Q numpy array with row indices (integers)
        of grid points in polyline.
    :return: columns_in_polyline: length-Q numpy array with column indices
        (integers) of grid points in polyline.
    """

    polyline_object_xy_metres = _polyline_from_vertex_arrays_to_linestring(
        vertex_x_coords_metres=polyline_x_coords_metres,
        vertex_y_coords_metres=polyline_y_coords_metres)

    x_spacing_metres = (
        grid_point_x_coords_metres[1] - grid_point_x_coords_metres[0])
    y_spacing_metres = (
        grid_point_y_coords_metres[1] - grid_point_y_coords_metres[0])

    x_min_to_consider_metres = numpy.min(
        polyline_x_coords_metres) - x_spacing_metres
    x_max_to_consider_metres = numpy.max(
        polyline_x_coords_metres) + x_spacing_metres
    y_min_to_consider_metres = numpy.min(
        polyline_y_coords_metres) - y_spacing_metres
    y_max_to_consider_metres = numpy.max(
        polyline_y_coords_metres) + y_spacing_metres

    x_in_range_indices = numpy.where(numpy.logical_and(
        grid_point_x_coords_metres >= x_min_to_consider_metres,
        grid_point_x_coords_metres <= x_max_to_consider_metres))[0]
    y_in_range_indices = numpy.where(numpy.logical_and(
        grid_point_y_coords_metres >= y_min_to_consider_metres,
        grid_point_y_coords_metres <= y_max_to_consider_metres))[0]

    row_offset = numpy.min(y_in_range_indices)
    column_offset = numpy.min(x_in_range_indices)

    grid_points_x_to_consider_metres = grid_point_x_coords_metres[
        x_in_range_indices]
    grid_points_y_to_consider_metres = grid_point_y_coords_metres[
        y_in_range_indices]

    rows_in_polyline = []
    columns_in_polyline = []
    num_rows_to_consider = len(grid_points_y_to_consider_metres)
    num_columns_to_consider = len(grid_points_x_to_consider_metres)

    for i in range(num_rows_to_consider):
        for j in range(num_columns_to_consider):
            this_grid_cell_edge_polygon_xy_metres = _grid_cell_to_polygon(
                grid_point_x_metres=grid_points_x_to_consider_metres[j],
                grid_point_y_metres=grid_points_y_to_consider_metres[i],
                x_spacing_metres=x_spacing_metres,
                y_spacing_metres=y_spacing_metres)

            this_intersection_flag = (
                this_grid_cell_edge_polygon_xy_metres.intersects(
                    polyline_object_xy_metres) or
                this_grid_cell_edge_polygon_xy_metres.touches(
                    polyline_object_xy_metres))
            if not this_intersection_flag:
                continue

            rows_in_polyline.append(i + row_offset)
            columns_in_polyline.append(j + column_offset)

    return numpy.array(rows_in_polyline), numpy.array(columns_in_polyline)


def _grid_points_to_binary_image(
        rows_in_object, columns_in_object, num_grid_rows, num_grid_columns):
    """Converts set of grid points in object to a binary image matrix.

    P = number of grid points in object
    M = number of grid rows (unique grid-point y-coordinates)
    N = number of grid columns (unique grid-point x-coordinates)

    :param rows_in_object: length-P numpy array with indices (integers) of rows
        in object.
    :param columns_in_object: length-P numpy array with indices (integers) of
        columns in object.
    :param num_grid_rows: Number of rows in grid.
    :param num_grid_columns: Number of columns in grid.
    :return: binary_matrix: M-by-N numpy array of Boolean flags.  If
        binary_matrix[i, j] = True, grid cell [i, j] is part of the object.
        Otherwise, grid cell [i, j] is *not* part of the object.
    """

    binary_matrix = numpy.full(
        (num_grid_rows, num_grid_columns), False, dtype=bool)
    binary_matrix[rows_in_object, columns_in_object] = True
    return binary_matrix


def _binary_image_to_grid_points(binary_matrix):
    """Converts binary image matrix to set of grid points in object.

    P = number of grid points in object
    M = number of grid rows (unique grid-point y-coordinates)
    N = number of grid columns (unique grid-point x-coordinates)

    :param binary_matrix: M-by-N numpy array of Boolean flags.  If
        binary_matrix[i, j] = True, grid cell [i, j] is part of the object.
        Otherwise, grid cell [i, j] is *not* part of the object.
    :return: rows_in_object: length-P numpy array with indices (integers) of
        rows in object.
    :return: columns_in_object: length-P numpy array with indices (integers) of
        columns in object.
    """

    return numpy.where(binary_matrix)


def _is_polyline_closed(vertex_latitudes_deg, vertex_longitudes_deg):
    """Determines whether or not polyline is closed.

    V = number of vertices

    :param vertex_latitudes_deg: length-V numpy array with latitudes (deg N) of
        vertices.
    :param vertex_longitudes_deg: length-V numpy array with longitudes (deg E)
        of vertices.
    :return: closed_flag: Boolean flag, indicating whether or not polyline is
        closed.
    """

    absolute_lat_diff_deg = numpy.absolute(
        vertex_latitudes_deg[0] - vertex_latitudes_deg[-1])
    absolute_lng_diff_deg = numpy.absolute(
        vertex_longitudes_deg[0] - vertex_longitudes_deg[-1])

    return (absolute_lat_diff_deg < TOLERANCE_DEG and
            absolute_lng_diff_deg < TOLERANCE_DEG)


def _close_frontal_grid_matrix(frontal_grid_matrix):
    """Performs binary closing on frontal grid.

    :param frontal_grid_matrix: See documentation for `frontal_grid_to_points`.
    :return: frontal_grid_matrix: Same as input, but after binary closing.
    """

    binary_warm_front_matrix = binary_closing(
        frontal_grid_matrix == WARM_FRONT_INTEGER_ID,
        structure=STRUCTURE_MATRIX_FOR_BINARY_CLOSING, origin=0, iterations=1)
    binary_cold_front_matrix = binary_closing(
        frontal_grid_matrix == COLD_FRONT_INTEGER_ID,
        structure=STRUCTURE_MATRIX_FOR_BINARY_CLOSING, origin=0, iterations=1)

    frontal_grid_matrix[
        numpy.where(binary_warm_front_matrix)] = WARM_FRONT_INTEGER_ID
    frontal_grid_matrix[
        numpy.where(binary_cold_front_matrix)] = COLD_FRONT_INTEGER_ID

    return frontal_grid_matrix


def _get_thermal_advection_over_grid(
        grid_relative_u_wind_matrix_m_s01, grid_relative_v_wind_matrix_m_s01,
        thermal_param_matrix_kelvins, grid_spacing_x_metres,
        grid_spacing_y_metres):
    """Computes instantaneous advection of thermal param at all points in grid.

    M = number of rows (unique grid-point y-coordinates)
    N = number of columns (unique grid-point x-coordinates)

    :param grid_relative_u_wind_matrix_m_s01: M-by-N numpy array with grid-
        relative u-wind components (in positive x-direction) (metres per
        second).
    :param grid_relative_v_wind_matrix_m_s01: Same as above, except for v-wind
        (in positive y-direction).
    :param thermal_param_matrix_kelvins: M-by-N numpy array with values of
        thermal parameter (examples: temperature, potential temperature,
        wet-bulb temperature, wet-bulb potential temperature, equivalent
        potential temperature).
    :param grid_spacing_x_metres: Distance between adjacent grid points in
        x-direction.
    :param grid_spacing_y_metres: Distance between adjacent grid points in
        y-direction.
    :return: advection_matrix_kelvins_s01: M-by-N numpy array with advection of
        thermal parameter (Kelvins per second) at each grid point.
    """

    y_gradient_matrix_kelvins_m01, x_gradient_matrix_kelvins_m01 = (
        numpy.gradient(
            thermal_param_matrix_kelvins, grid_spacing_y_metres,
            grid_spacing_x_metres))

    advection_matrix_kelvins_s01 = -(
        grid_relative_u_wind_matrix_m_s01 * x_gradient_matrix_kelvins_m01 +
        grid_relative_v_wind_matrix_m_s01 * y_gradient_matrix_kelvins_m01)
    return advection_matrix_kelvins_s01


def check_front_type(front_string_id):
    """Ensures that front type is valid.

    :param front_string_id: String ID for front type.
    :raises: ValueError: if front type is unrecognized.
    """

    error_checking.assert_is_string(front_string_id)
    if front_string_id not in VALID_STRING_IDS:
        error_string = (
            '\n\n' + str(VALID_STRING_IDS) +
            '\n\nValid front types (listed above) do not include "' +
            front_string_id + '".')
        raise ValueError(error_string)


def buffer_distance_to_narr_mask(buffer_distance_metres):
    """Converts buffer distance to mask defined over NARR grid.

    m = number of rows (unique grid-point y-coordinates) within buffer distance
    n = number of columns (unique grid-point x-coordinates) within buffer
        distance

    :param buffer_distance_metres: Buffer distance.
    :return: mask_matrix: m-by-n numpy array of Boolean flags.  The center point
        -- mask_matrix[floor(m/2), floor(n/2)] -- represents the grid point
        around which the buffer is applied.  If mask_matrix[i, j] = True, grid
        point [i, j] -- in this relative coordinate system -- is within the
        distance buffer.
    """

    error_checking.assert_is_greater(buffer_distance_metres, 0.)
    buffer_distance_metres = max([buffer_distance_metres, 1.])

    grid_spacing_metres, _ = nwp_model_utils.get_xy_grid_spacing(
        model_name=nwp_model_utils.NARR_MODEL_NAME)
    max_row_or_column_offset = int(
        numpy.floor(float(buffer_distance_metres) / grid_spacing_metres))

    row_or_column_offsets = numpy.linspace(
        -max_row_or_column_offset, max_row_or_column_offset,
        num=2*max_row_or_column_offset + 1, dtype=int)

    column_offset_matrix, row_offset_matrix = grids.xy_vectors_to_matrices(
        x_unique_metres=row_or_column_offsets,
        y_unique_metres=row_or_column_offsets)
    row_offset_matrix = row_offset_matrix.astype(float)
    column_offset_matrix = column_offset_matrix.astype(float)

    distance_matrix_metres = grid_spacing_metres * numpy.sqrt(
        row_offset_matrix ** 2 + column_offset_matrix ** 2)
    return distance_matrix_metres <= buffer_distance_metres


def dilate_ternary_narr_image(ternary_matrix, dilation_distance_metres=None,
                              dilation_kernel_matrix=None):
    """Dilates a ternary image on the NARR grid.

    M = number of rows (unique grid-point y-coordinates) in NARR grid
    N = number of columns (unique grid-point x-coordinates) in NARR grid

    :param ternary_matrix: M-by-N numpy array of integers (must be all 0, 1,
        or 2).
    :param dilation_distance_metres: See documentation for
        `dilate_binary_narr_image`.
    :param dilation_kernel_matrix: See documentation for
        `dilate_binary_narr_image`.
    :return: ternary_matrix: Same as input, except dilated.
    """

    error_checking.assert_is_numpy_array(ternary_matrix, num_dimensions=2)
    error_checking.assert_is_integer_numpy_array(ternary_matrix)
    error_checking.assert_is_geq_numpy_array(ternary_matrix, 0)
    error_checking.assert_is_leq_numpy_array(ternary_matrix, 2)

    binary_cold_front_matrix = numpy.full(
        ternary_matrix.shape, NO_FRONT_INTEGER_ID, dtype=int)
    binary_cold_front_matrix[
        ternary_matrix == COLD_FRONT_INTEGER_ID] = ANY_FRONT_INTEGER_ID
    binary_cold_front_matrix = dilate_binary_narr_image(
        binary_cold_front_matrix,
        dilation_distance_metres=dilation_distance_metres,
        dilation_kernel_matrix=dilation_kernel_matrix)

    binary_warm_front_matrix = numpy.full(
        ternary_matrix.shape, NO_FRONT_INTEGER_ID, dtype=int)
    binary_warm_front_matrix[
        ternary_matrix == WARM_FRONT_INTEGER_ID] = ANY_FRONT_INTEGER_ID
    binary_warm_front_matrix = dilate_binary_narr_image(
        binary_warm_front_matrix,
        dilation_distance_metres=dilation_distance_metres,
        dilation_kernel_matrix=dilation_kernel_matrix)

    cold_front_row_indices, cold_front_column_indices = numpy.where(
        ternary_matrix == COLD_FRONT_INTEGER_ID)
    warm_front_row_indices, warm_front_column_indices = numpy.where(
        ternary_matrix == WARM_FRONT_INTEGER_ID)
    both_fronts_row_indices, both_fronts_column_indices = numpy.where(
        numpy.logical_and(binary_cold_front_matrix == ANY_FRONT_INTEGER_ID,
                          binary_warm_front_matrix == ANY_FRONT_INTEGER_ID))

    num_points_to_resolve = len(both_fronts_row_indices)
    for i in range(num_points_to_resolve):
        these_row_diffs = both_fronts_row_indices[i] - cold_front_row_indices
        these_column_diffs = (
            both_fronts_column_indices[i] - cold_front_column_indices)
        this_min_cold_front_distance = numpy.min(
            these_row_diffs**2 + these_column_diffs**2)

        these_row_diffs = both_fronts_row_indices[i] - warm_front_row_indices
        these_column_diffs = (
            both_fronts_column_indices[i] - warm_front_column_indices)
        this_min_warm_front_distance = numpy.min(
            these_row_diffs**2 + these_column_diffs**2)

        if this_min_cold_front_distance <= this_min_warm_front_distance:
            binary_warm_front_matrix[
                both_fronts_row_indices[i],
                both_fronts_column_indices[i]] = NO_FRONT_INTEGER_ID
        else:
            binary_cold_front_matrix[
                both_fronts_row_indices[i],
                both_fronts_column_indices[i]] = NO_FRONT_INTEGER_ID

    ternary_matrix[
        binary_cold_front_matrix == ANY_FRONT_INTEGER_ID
    ] = COLD_FRONT_INTEGER_ID
    ternary_matrix[
        binary_warm_front_matrix == ANY_FRONT_INTEGER_ID
        ] = WARM_FRONT_INTEGER_ID
    return ternary_matrix


def dilate_binary_narr_image(binary_matrix, dilation_distance_metres=None,
                             dilation_kernel_matrix=None):
    """Dilates a binary image on the NARR grid.

    M = number of rows (unique grid-point y-coordinates) in NARR grid
    N = number of columns (unique grid-point x-coordinates) in NARR grid
    m = number of rows in dilation kernel
    n = number of columns in dilation kernel

    If `dilation_kernel_matrix` is None, `dilation_distance_metres` will be
    used.

    :param binary_matrix: M-by-N numpy array of integers (must be all 0 or 1).
    :param dilation_distance_metres: Dilation distance.
    :param dilation_kernel_matrix: m-by-n numpy array of integers (all 0 or 1).
        This may be created by `buffer_distance_to_narr_mask` for a given buffer
        distance.
    :return: binary_matrix: Same as input, except dilated.
    """

    error_checking.assert_is_numpy_array(binary_matrix, num_dimensions=2)
    error_checking.assert_is_integer_numpy_array(binary_matrix)
    error_checking.assert_is_geq_numpy_array(binary_matrix, 0)
    error_checking.assert_is_leq_numpy_array(binary_matrix, 1)

    if dilation_kernel_matrix is None:
        dilation_kernel_matrix = buffer_distance_to_narr_mask(
            dilation_distance_metres).astype(int)

    error_checking.assert_is_numpy_array(
        dilation_kernel_matrix, num_dimensions=2)
    error_checking.assert_is_integer_numpy_array(dilation_kernel_matrix)
    error_checking.assert_is_geq_numpy_array(dilation_kernel_matrix, 0)
    error_checking.assert_is_leq_numpy_array(dilation_kernel_matrix, 1)
    error_checking.assert_is_geq(numpy.sum(dilation_kernel_matrix), 1)

    binary_matrix = cv2.dilate(
        binary_matrix.astype(numpy.uint8),
        dilation_kernel_matrix.astype(numpy.uint8), iterations=1)
    return binary_matrix.astype(int)


def frontal_grid_to_points(frontal_grid_matrix):
    """Converts a frontal grid to lists of points.

    M = number of rows (unique grid-point y-coordinates)
    N = number of columns (unique grid-point x-coordinates)
    W = number of grid cells intersected by warm front
    C = number of grid cells intersected by cold front

    :param frontal_grid_matrix: M-by-N numpy array of integers.  If
        frontal_grid_matrix[i, j] = 0, there is no front intersecting grid point
        [i, j].  If frontal_grid_matrix[i, j] = 1, there is a warm front
        intersecting grid point [i, j].  If frontal_grid_matrix[i, j] = 2, there
        is a cold front intersecting grid point [i, j].
    :return: frontal_grid_dict: Dictionary with the following keys.
    frontal_grid_dict['warm_front_row_indices']: length-W numpy array with row
        indices (integers) of grid cells intersected by a warm front.
    frontal_grid_dict['warm_front_column_indices']: Same as above, except for
        columns.
    frontal_grid_dict['cold_front_row_indices']: length-C numpy array with row
        indices (integers) of grid cells intersected by a cold front.
    frontal_grid_dict['cold_front_column_indices']: Same as above, except for
        columns.
    """

    error_checking.assert_is_integer_numpy_array(frontal_grid_matrix)
    error_checking.assert_is_numpy_array(frontal_grid_matrix, num_dimensions=2)
    error_checking.assert_is_geq_numpy_array(
        frontal_grid_matrix, NO_FRONT_INTEGER_ID)
    error_checking.assert_is_leq_numpy_array(
        frontal_grid_matrix, COLD_FRONT_INTEGER_ID)

    warm_front_row_indices, warm_front_column_indices = numpy.where(
        frontal_grid_matrix == WARM_FRONT_INTEGER_ID)
    cold_front_row_indices, cold_front_column_indices = numpy.where(
        frontal_grid_matrix == COLD_FRONT_INTEGER_ID)

    return {
        WARM_FRONT_ROW_INDICES_COLUMN: warm_front_row_indices,
        WARM_FRONT_COLUMN_INDICES_COLUMN: warm_front_column_indices,
        COLD_FRONT_ROW_INDICES_COLUMN: cold_front_row_indices,
        COLD_FRONT_COLUMN_INDICES_COLUMN: cold_front_column_indices
    }


def frontal_points_to_grid(frontal_grid_dict, num_grid_rows, num_grid_columns):
    """Converts lists of frontal points to a grid.

    :param frontal_grid_dict: See documentation for `frontal_grid_to_points`.
    :param num_grid_rows: Number of rows (unique grid-point y-coordinates).
    :param num_grid_columns: Number of columns (unique grid-point
        x-coordinates).
    :return: frontal_grid_matrix: See documentation for
        `frontal_grid_to_points`.
    """

    frontal_grid_matrix = numpy.full(
        (num_grid_rows, num_grid_columns), NO_FRONT_INTEGER_ID, dtype=int)

    frontal_grid_matrix[
        frontal_grid_dict[WARM_FRONT_ROW_INDICES_COLUMN],
        frontal_grid_dict[WARM_FRONT_COLUMN_INDICES_COLUMN]
    ] = WARM_FRONT_INTEGER_ID
    frontal_grid_matrix[
        frontal_grid_dict[COLD_FRONT_ROW_INDICES_COLUMN],
        frontal_grid_dict[COLD_FRONT_COLUMN_INDICES_COLUMN]
    ] = COLD_FRONT_INTEGER_ID

    return frontal_grid_matrix


def frontal_grid_to_regions(frontal_grid_matrix):
    """Converts frontal grid to a list of connected regions (objects).

    N = number of regions
    P_i = number of grid points in the [i]th region

    :param frontal_grid_matrix: See documentation for `frontal_grid_to_points`.
    :return: frontal_region_dict: Dictionary with the following keys.
    frontal_region_dict['row_indices_by_region']: length-N list, where the [i]th
        element is a numpy array (length P_i) with indices of grid rows in the
        [i]th region.
    frontal_region_dict['column_indices_by_region']: Same as above, except for
        columns.
    frontal_region_dict['front_type_by_region']: length-N list, where each
        element is a string (either "warm" or "cold") identifying the front
        type.
    """

    frontal_grid_matrix = _close_frontal_grid_matrix(frontal_grid_matrix)
    region_matrix = label_image(frontal_grid_matrix, connectivity=2)

    num_regions = numpy.max(region_matrix)
    row_indices_by_region = [[]] * num_regions
    column_indices_by_region = [[]] * num_regions
    front_type_by_region = [''] * num_regions

    for i in range(num_regions):
        row_indices_by_region[i], column_indices_by_region[i] = numpy.where(
            region_matrix == i + 1)
        this_integer_id = frontal_grid_matrix[
            row_indices_by_region[i][0], column_indices_by_region[i][0]]

        if this_integer_id == WARM_FRONT_INTEGER_ID:
            front_type_by_region[i] = WARM_FRONT_STRING_ID
        elif this_integer_id == COLD_FRONT_INTEGER_ID:
            front_type_by_region[i] = COLD_FRONT_STRING_ID

    return {
        ROW_INDICES_BY_REGION_KEY: row_indices_by_region,
        COLUMN_INDICES_BY_REGION_KEY: column_indices_by_region,
        FRONT_TYPE_BY_REGION_KEY: front_type_by_region
    }


def get_frontal_types_over_grid(
        grid_relative_u_wind_matrix_m_s01, grid_relative_v_wind_matrix_m_s01,
        thermal_param_matrix_kelvins, binary_matrix, grid_spacing_x_metres,
        grid_spacing_y_metres):
    """Determines front type at each point in grid.

    M = number of rows (unique grid-point y-coordinates)
    N = number of columns (unique grid-point x-coordinates)

    :param grid_relative_u_wind_matrix_m_s01: See documentation for
        `_get_thermal_advection_over_grid`.
    :param grid_relative_v_wind_matrix_m_s01: See doc for
        `_get_thermal_advection_over_grid`.
    :param thermal_param_matrix_kelvins: See doc for
        `_get_thermal_advection_over_grid`.
    :param binary_matrix: M-by-N numpy array of Boolean flags.  If
        binary_matrix[i, j] = True, a front passes through grid point [i, j].
    :param grid_spacing_x_metres: See doc for
        `_get_thermal_advection_over_grid`.
    :param grid_spacing_y_metres: See doc for
        `_get_thermal_advection_over_grid`.
    :return: frontal_grid_matrix: See doc for `frontal_grid_to_points`.
    """

    # TODO(thunderhoser): This is still primitive (advection calculation at each
    # grid point is based on wind at said grid point and first-order finite
    # difference of temperature).  Need to get fancier.

    thermal_advection_matrix_kelvins_m01 = _get_thermal_advection_over_grid(
        grid_relative_u_wind_matrix_m_s01, grid_relative_v_wind_matrix_m_s01,
        thermal_param_matrix_kelvins, grid_spacing_x_metres,
        grid_spacing_y_metres)

    warm_front_row_indices, warm_front_column_indices = numpy.where(
        numpy.logical_and(
            thermal_advection_matrix_kelvins_m01 > 0., binary_matrix))
    cold_front_row_indices, cold_front_column_indices = numpy.where(
        numpy.logical_and(
            thermal_advection_matrix_kelvins_m01 <= 0., binary_matrix))

    num_grid_rows = binary_matrix.shape[0]
    num_grid_columns = binary_matrix.shape[1]
    frontal_grid_matrix = numpy.full(
        (num_grid_rows, num_grid_columns), NO_FRONT_INTEGER_ID, dtype=int)

    frontal_grid_matrix[warm_front_row_indices,
                        warm_front_column_indices] = WARM_FRONT_INTEGER_ID
    frontal_grid_matrix[cold_front_row_indices,
                        cold_front_column_indices] = COLD_FRONT_INTEGER_ID
    return frontal_grid_matrix


def polyline_to_binary_narr_grid(
        polyline_latitudes_deg, polyline_longitudes_deg,
        dilation_distance_metres):
    """Converts polyline to binary image with dimensions of NARR* grid.

    * NARR = North American Regional Reanalysis

    P = number of vertices in polyline
    M = number of rows in NARR grid = 277
    N = number of columns in NARR grid = 349

    :param polyline_latitudes_deg: length-P numpy array with latitudes (deg N)
        in polyline.
    :param polyline_longitudes_deg: length-P numpy array with longitudes (deg E)
        in polyline.
    :param dilation_distance_metres: Dilation distance.
    :return: binary_matrix: M-by-N numpy array of Boolean flags.  If
        binary_matrix[i, j] = True, the polyline passes through grid cell
        [i, j].  Otherwise, the polyline does not pass through grid cell [i, j].
    """

    error_checking.assert_is_geq(dilation_distance_metres, 0.)
    dilation_distance_metres = max([dilation_distance_metres, 1.])

    polyline_x_coords_metres, polyline_y_coords_metres = (
        nwp_model_utils.project_latlng_to_xy(
            latitudes_deg=polyline_latitudes_deg,
            longitudes_deg=polyline_longitudes_deg,
            model_name=nwp_model_utils.NARR_MODEL_NAME))

    grid_point_x_coords_metres, grid_point_y_coords_metres = (
        nwp_model_utils.get_xy_grid_points(
            model_name=nwp_model_utils.NARR_MODEL_NAME))

    rows_in_polyline, columns_in_polyline = _polyline_to_grid_points(
        polyline_x_coords_metres=polyline_x_coords_metres,
        polyline_y_coords_metres=polyline_y_coords_metres,
        grid_point_x_coords_metres=grid_point_x_coords_metres,
        grid_point_y_coords_metres=grid_point_y_coords_metres)

    num_grid_rows, num_grid_columns = nwp_model_utils.get_grid_dimensions(
        model_name=nwp_model_utils.NARR_MODEL_NAME)

    binary_matrix = _grid_points_to_binary_image(
        rows_in_object=rows_in_polyline, columns_in_object=columns_in_polyline,
        num_grid_rows=num_grid_rows, num_grid_columns=num_grid_columns)

    return dilate_binary_narr_image(
        binary_matrix=binary_matrix,
        dilation_distance_metres=dilation_distance_metres)


def many_polylines_to_narr_grid(front_table, dilation_distance_metres):
    """For each time step, converts frontal polylines to image over NARR* grid.

    * NARR = North American Regional Reanalysis

    M = number of rows in NARR grid = 277
    N = number of columns in NARR grid = 349
    W = number of grid cells intersected by warm front at a given valid time
    C = number of grid cells intersected by cold front at a given valid time

    :param front_table: See documentation for
        `fronts_io.write_polylines_to_file`.
    :param dilation_distance_metres: Dilation distance.
    :return: frontal_grid_table: pandas DataFrame with the following columns.
        Each row is one valid time.
    frontal_grid_table.unix_time_sec: Valid time.
    frontal_grid_table.warm_front_row_indices: length-W numpy array with row
        indices (integers) of grid cells intersected by a warm front.
    frontal_grid_table.warm_front_column_indices: Same as above, except for
        columns.
    frontal_grid_table.cold_front_row_indices: length-C numpy array with row
        indices (integers) of grid cells intersected by a cold front.
    frontal_grid_table.cold_front_column_indices: Same as above, except for
        columns.
    """

    num_grid_rows, num_grid_columns = nwp_model_utils.get_grid_dimensions(
        model_name=nwp_model_utils.NARR_MODEL_NAME)

    valid_times_unix_sec = numpy.unique(front_table[TIME_COLUMN].values)
    valid_time_strings = [
        time_conversion.unix_sec_to_string(t, TIME_FORMAT_FOR_LOG_MESSAGES)
        for t in valid_times_unix_sec]
    num_valid_times = len(valid_times_unix_sec)

    warm_front_row_indices_by_time = [[]] * num_valid_times
    warm_front_column_indices_by_time = [[]] * num_valid_times
    cold_front_row_indices_by_time = [[]] * num_valid_times
    cold_front_column_indices_by_time = [[]] * num_valid_times

    for i in range(num_valid_times):
        print ('Converting frontal polylines to image over NARR grid for '
               '{0:s}...').format(valid_time_strings[i])

        these_front_indices = numpy.where(
            front_table[TIME_COLUMN].values == valid_times_unix_sec[i])[0]
        this_frontal_grid_matrix = numpy.full(
            (num_grid_rows, num_grid_columns), NO_FRONT_INTEGER_ID, dtype=int)

        for j in these_front_indices:
            skip_this_front = _is_polyline_closed(
                vertex_latitudes_deg=front_table[LATITUDES_COLUMN].values[j],
                vertex_longitudes_deg=front_table[LONGITUDES_COLUMN].values[j])
            if skip_this_front:
                this_num_points = len(front_table[LATITUDES_COLUMN].values[j])
                print ('SKIPPING front with {0:d} points (closed '
                       'polyline).').format(this_num_points)
                continue

            this_binary_matrix = polyline_to_binary_narr_grid(
                polyline_latitudes_deg=
                front_table[LATITUDES_COLUMN].values[j],
                polyline_longitudes_deg=
                front_table[LONGITUDES_COLUMN].values[j],
                dilation_distance_metres=dilation_distance_metres)

            if front_table[FRONT_TYPE_COLUMN].values[j] == WARM_FRONT_STRING_ID:
                this_frontal_grid_matrix[
                    numpy.where(this_binary_matrix)] = WARM_FRONT_INTEGER_ID

            elif (front_table[FRONT_TYPE_COLUMN].values[i] ==
                  COLD_FRONT_STRING_ID):
                this_frontal_grid_matrix[
                    numpy.where(this_binary_matrix)] = COLD_FRONT_INTEGER_ID

        this_frontal_grid_dict = frontal_grid_to_points(
            this_frontal_grid_matrix)
        warm_front_row_indices_by_time[i] = this_frontal_grid_dict[
            WARM_FRONT_ROW_INDICES_COLUMN]
        warm_front_column_indices_by_time[i] = this_frontal_grid_dict[
            WARM_FRONT_COLUMN_INDICES_COLUMN]
        cold_front_row_indices_by_time[i] = this_frontal_grid_dict[
            COLD_FRONT_ROW_INDICES_COLUMN]
        cold_front_column_indices_by_time[i] = this_frontal_grid_dict[
            COLD_FRONT_COLUMN_INDICES_COLUMN]

    frontal_grid_dict = {
        TIME_COLUMN: valid_times_unix_sec,
        WARM_FRONT_ROW_INDICES_COLUMN: warm_front_row_indices_by_time,
        WARM_FRONT_COLUMN_INDICES_COLUMN: warm_front_column_indices_by_time,
        COLD_FRONT_ROW_INDICES_COLUMN: cold_front_row_indices_by_time,
        COLD_FRONT_COLUMN_INDICES_COLUMN: cold_front_column_indices_by_time
    }
    return pandas.DataFrame.from_dict(frontal_grid_dict)
