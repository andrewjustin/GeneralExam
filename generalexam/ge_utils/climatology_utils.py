"""Methods for creating climatology of fronts."""

import os.path
import numpy
import netCDF4
from gewittergefahr.gg_utils import time_conversion
from gewittergefahr.gg_utils import file_system_utils
from gewittergefahr.gg_utils import error_checking
from generalexam.ge_utils import front_utils

WINTER_STRING = 'winter'
SPRING_STRING = 'spring'
SUMMER_STRING = 'summer'
FALL_STRING = 'fall'

VALID_SEASON_STRINGS = [
    WINTER_STRING, SPRING_STRING, SUMMER_STRING, FALL_STRING
]

FILE_NAME_TIME_FORMAT = '%Y-%m-%d-%H%M%S'

ROW_DIMENSION_KEY = 'row'
COLUMN_DIMENSION_KEY = 'column'
PREDICTION_FILE_DIM_KEY = 'prediction_file'
PREDICTION_FILE_CHAR_DIM_KEY = 'prediction_file_char'

NUM_WF_LABELS_KEY = 'num_wf_labels_matrix'
NUM_CF_LABELS_KEY = 'num_cf_labels_matrix'
NUM_UNIQUE_WF_KEY = 'num_unique_wf_matrix'
NUM_UNIQUE_CF_KEY = 'num_unique_cf_matrix'
FIRST_TIME_KEY = 'first_time_unix_sec'
LAST_TIME_KEY = 'last_time_unix_sec'
HOURS_KEY = 'hours'
MONTHS_KEY = 'months'
PREDICTION_FILES_KEY = 'prediction_file_names'
SEPARATION_TIME_KEY = 'separation_time_sec'


def _check_season(season_string):
    """Error-checks season.

    :param season_string: Season.
    :raises: ValueError: if `season_string not in VALID_SEASON_STRINGS`.
    """

    error_checking.assert_is_string(season_string)

    if season_string not in VALID_SEASON_STRINGS:
        error_string = (
            '\n\n{0:s}\nValid seasons (listed above) do not include "{1:s}".'
        ).format(str(VALID_SEASON_STRINGS), season_string)

        raise ValueError(error_string)


def _check_hours(hours):
    """Error-checks list of hours.

    :param hours: 1-D numpy array of hours (in range 0...23).
    """

    error_checking.assert_is_numpy_array(hours, num_dimensions=1)
    error_checking.assert_is_integer_numpy_array(hours)
    error_checking.assert_is_geq_numpy_array(hours, 0)
    error_checking.assert_is_leq_numpy_array(hours, 23)


def _check_months(months):
    """Error-checks list of months.

    :param months: 1-D numpy array of months (in range 1...12).
    """

    error_checking.assert_is_numpy_array(months, num_dimensions=1)
    error_checking.assert_is_integer_numpy_array(months)
    error_checking.assert_is_geq_numpy_array(months, 1)
    error_checking.assert_is_leq_numpy_array(months, 12)


def _exact_times_to_hours(exact_times_unix_sec):
    """Converts exact times to hours.

    N = number of times

    :param exact_times_unix_sec: length-N numpy array of exact times.
    :return: hours: length-N numpy array of hours (in range 0...23).
    """

    error_checking.assert_is_integer_numpy_array(exact_times_unix_sec)
    error_checking.assert_is_numpy_array(exact_times_unix_sec, num_dimensions=1)

    hours = [
        int(time_conversion.unix_sec_to_string(t, '%H'))
        for t in exact_times_unix_sec
    ]

    return numpy.array(hours, dtype=int)


def _exact_times_to_months(exact_times_unix_sec):
    """Converts exact times to months.

    N = number of times

    :param exact_times_unix_sec: length-N numpy array of exact times.
    :return: months: length-N numpy array of months (in range 1...12).
    """

    error_checking.assert_is_integer_numpy_array(exact_times_unix_sec)
    error_checking.assert_is_numpy_array(exact_times_unix_sec, num_dimensions=1)

    months = [
        int(time_conversion.unix_sec_to_string(t, '%m'))
        for t in exact_times_unix_sec
    ]

    return numpy.array(months, dtype=int)


def _apply_sep_time_one_front_type(
        front_type_enums, valid_times_unix_sec, separation_time_sec,
        relevant_front_type_enum):
    """Applies separation time for one front type (warm or cold).

    :param front_type_enums: Same as input arg for `apply_separation_time`,
        except this method assumes the array is sorted by increasing time.
    :param valid_times_unix_sec: Same as input arg for `apply_separation_time`,
        except this method assumes the array is sorted by increasing time.
    :param separation_time_sec: See doc for `apply_separation_time`.
    :param relevant_front_type_enum: Will apply separation time only for this
        front type (must be in `front_utils.VALID_FRONT_TYPE_ENUMS`).
    :return: front_type_enums: Same as input, except that some labels of
        `relevant_front_type_enum` may have been changed to "no front".
    """

    time_steps_sec = numpy.diff(valid_times_unix_sec)
    smallest_time_step_sec = numpy.min(time_steps_sec)

    while True:
        orig_front_type_enums = front_type_enums + 0

        frontal_flags = front_type_enums == relevant_front_type_enum

        prev_non_frontal_flags = numpy.logical_or(
            time_steps_sec > smallest_time_step_sec,
            front_type_enums[:-1] != relevant_front_type_enum
        )

        prev_non_frontal_flags = numpy.concatenate((
            numpy.array([1], dtype=bool),
            prev_non_frontal_flags
        ))

        front_start_indices = numpy.where(
            numpy.logical_and(frontal_flags, prev_non_frontal_flags)
        )[0]

        for k in front_start_indices:
            if front_type_enums[k] != relevant_front_type_enum:
                continue

            these_indices = numpy.where(numpy.logical_and(
                front_type_enums == relevant_front_type_enum,
                valid_times_unix_sec <
                valid_times_unix_sec[k] + separation_time_sec
            ))[0]

            these_indices = these_indices[these_indices > k]
            if len(these_indices) == 0:
                continue

            front_type_enums[these_indices] = front_utils.NO_FRONT_ENUM

        if numpy.array_equal(front_type_enums, orig_front_type_enums):
            break

    return front_type_enums


def season_to_months(season_string):
    """Returns months in season.

    :param season_string: Season (must be accepted by `_check_season`).
    :return: months: 1-D numpy array of months (in range 1...12).
    """

    _check_season(season_string)

    if season_string == WINTER_STRING:
        return numpy.array([12, 1, 2], dtype=int)
    if season_string == SPRING_STRING:
        return numpy.array([3, 4, 5], dtype=int)
    if season_string == SUMMER_STRING:
        return numpy.array([6, 7, 8], dtype=int)

    return numpy.array([9, 10, 11], dtype=int)


def filter_by_hour(all_times_unix_sec, hours_to_keep):
    """Filters times by hour.

    :param all_times_unix_sec: 1-D numpy array of times.
    :param hours_to_keep: 1-D numpy array of hours to keep (integers in 0...23).
    :return: indices_to_keep: 1-D numpy array of indices to keep.
        If `k in indices_to_keep`, then unix_times_sec[k] has one of the desired
        hours.
    """

    _check_hours(hours_to_keep)
    all_hours = _exact_times_to_hours(all_times_unix_sec)

    num_times = len(all_times_unix_sec)
    keep_time_flags = numpy.full(num_times, False, dtype=bool)

    for this_hour in hours_to_keep:
        keep_time_flags = numpy.logical_or(
            keep_time_flags, all_hours == this_hour
        )

    return numpy.where(keep_time_flags)[0]


def filter_by_month(all_times_unix_sec, months_to_keep):
    """Filters times by month.

    :param all_times_unix_sec: 1-D numpy array of times.
    :param months_to_keep: 1-D numpy array of months to keep (integers in
        1...12).
    :return: indices_to_keep: 1-D numpy array of indices to keep.
        If `k in indices_to_keep`, then unix_times_sec[k] has one of the desired
        months.
    """

    _check_months(months_to_keep)
    all_months = _exact_times_to_months(all_times_unix_sec)

    num_times = len(all_times_unix_sec)
    keep_time_flags = numpy.full(num_times, False, dtype=bool)

    for this_month in months_to_keep:
        keep_time_flags = numpy.logical_or(
            keep_time_flags, all_months == this_month
        )

    return numpy.where(keep_time_flags)[0]


def months_to_string(months):
    """Converts list of months to two strings.

    For example, if the months are {1, 2, 12}, this method will return the
    following strings.

    - Verbose string: "Jan, Feb, Dec"
    - Abbrev: "jfd"

    :param months: 1-D numpy array of months (integers in 1...12).
    :return: verbose_string: See general discussion above.
    :return: abbrev_string: See general discussion above.
    """

    _check_months(months)

    dummy_time_strings = [
        '4055-{0:02d}'.format(m) for m in numpy.sort(months)
    ]

    dummy_times_unix_sec = numpy.array([
        time_conversion.string_to_unix_sec(s, '%Y-%m')
        for s in dummy_time_strings
    ], dtype=int)

    month_strings = [
        time_conversion.unix_sec_to_string(t, '%b')
        for t in dummy_times_unix_sec
    ]

    verbose_string = ', '.join(month_strings)
    abbrev_string = ''.join([s[0].lower() for s in month_strings])
    return verbose_string, abbrev_string


def hours_to_string(hours):
    """Converts list of hours to two strings.

    For example, if the hours are {12, 13, 14, 15, 16, 17}, this method will
    return the following strings.

    - Verbose string: "12, 13, 14, 15, 16, 17 UTC"
    - Abbrev: "12-13-14-15-16-17utc"

    :param hours: 1-D numpy array of hours (in range 0...23).
    :return: verbose_string: See general discussion above.
    :return: abbrev_string: See general discussion above.
    """

    _check_hours(hours)

    dummy_time_strings = [
        '4055-01-01-{0:02d}'.format(h) for h in numpy.sort(hours)
    ]

    dummy_times_unix_sec = numpy.array([
        time_conversion.string_to_unix_sec(s, '%Y-%m-%d-%H')
        for s in dummy_time_strings
    ], dtype=int)

    hour_strings = [
        time_conversion.unix_sec_to_string(t, '%H')
        for t in dummy_times_unix_sec
    ]

    verbose_string = '{0:s} UTC'.format(', '.join(hour_strings))
    abbrev_string = '{0:s}utc'.format('-'.join(hour_strings))
    return verbose_string, abbrev_string


def apply_separation_time(front_type_enums, valid_times_unix_sec,
                          separation_time_sec):
    """Applies separation time to front labels.

    T = number of time steps

    :param front_type_enums: length-T numpy array of front labels (must be in
        `front_utils.VALID_FRONT_TYPE_ENUMS`).
    :param valid_times_unix_sec: length-T numpy array of valid times.
    :param separation_time_sec: Separation time.
    :return: front_type_enums: Same as input but with two exceptions.
        [1] Some labels may have been changed to "no front".
        [2] Sorted by increasing time.

    :return: valid_times_unix_sec: Same as input but sorted by increasing time.
    """

    error_checking.assert_is_integer_numpy_array(front_type_enums)
    error_checking.assert_is_numpy_array(front_type_enums, num_dimensions=1)
    error_checking.assert_is_geq_numpy_array(
        front_type_enums, numpy.min(front_utils.VALID_FRONT_TYPE_ENUMS)
    )
    error_checking.assert_is_leq_numpy_array(
        front_type_enums, numpy.max(front_utils.VALID_FRONT_TYPE_ENUMS)
    )

    num_times = len(front_type_enums)
    error_checking.assert_is_integer_numpy_array(valid_times_unix_sec)
    error_checking.assert_is_numpy_array(
        valid_times_unix_sec,
        exact_dimensions=numpy.array([num_times], dtype=int)
    )

    error_checking.assert_is_integer(separation_time_sec)
    error_checking.assert_is_greater(separation_time_sec, 0)

    sort_indices = numpy.argsort(valid_times_unix_sec)
    valid_times_unix_sec = valid_times_unix_sec[sort_indices]
    front_type_enums = front_type_enums[sort_indices]

    front_type_enums = _apply_sep_time_one_front_type(
        front_type_enums=front_type_enums,
        valid_times_unix_sec=valid_times_unix_sec,
        separation_time_sec=separation_time_sec,
        relevant_front_type_enum=front_utils.WARM_FRONT_ENUM)

    front_type_enums = _apply_sep_time_one_front_type(
        front_type_enums=front_type_enums,
        valid_times_unix_sec=valid_times_unix_sec,
        separation_time_sec=separation_time_sec,
        relevant_front_type_enum=front_utils.COLD_FRONT_ENUM)

    return front_type_enums, valid_times_unix_sec


def find_gridded_count_file(
        directory_name, first_time_unix_sec, last_time_unix_sec, hours=None,
        months=None, raise_error_if_missing=True):
    """Locates file with gridded front counts.

    :param directory_name: Directory name.
    :param first_time_unix_sec: First time in period.
    :param last_time_unix_sec: Last time in period.
    :param hours: 1-D numpy array of hours for which fronts were counted.  If
        all hours were used, leave this as None.
    :param months: Same but for months.
    :param raise_error_if_missing: Boolean flag.  If file is missing and
        `raise_error_if_missing = True`, this method will error out.
    :return: netcdf_file_name: Path to file with gridded counts.  If file is
        missing and `raise_error_if_missing = False`, this is the *expected*
        path.
    """

    error_checking.assert_is_string(directory_name)
    error_checking.assert_is_integer(first_time_unix_sec)
    error_checking.assert_is_integer(last_time_unix_sec)
    error_checking.assert_is_greater(last_time_unix_sec, first_time_unix_sec)
    error_checking.assert_is_boolean(raise_error_if_missing)

    if hours is None:
        hour_string = 'all'
    else:
        hour_string = hours_to_string(hours)[-1]

    if months is None:
        month_string = 'all'
    else:
        month_string = months_to_string(months)[-1]

    netcdf_file_name = (
        '{0:s}/gridded-front-counts_{1:s}_{2:s}_hours={3:s}_months={4:s}.nc'
    ).format(
        directory_name,
        time_conversion.unix_sec_to_string(
            first_time_unix_sec, FILE_NAME_TIME_FORMAT),
        time_conversion.unix_sec_to_string(
            last_time_unix_sec, FILE_NAME_TIME_FORMAT),
        hour_string, month_string
    )

    if raise_error_if_missing and not os.path.isfile(netcdf_file_name):
        error_string = 'Cannot find file.  Expected at: "{0:s}"'.format(
            netcdf_file_name)
        raise ValueError(error_string)

    return netcdf_file_name


def write_gridded_counts(
        netcdf_file_name, num_wf_labels_matrix, num_cf_labels_matrix,
        num_unique_wf_matrix, num_unique_cf_matrix, first_time_unix_sec,
        last_time_unix_sec, prediction_file_names, separation_time_sec,
        hours=None, months=None):
    """Writes gridded front counts to NetCDF file.

    M = number of rows in grid
    N = number of columns in grid

    :param netcdf_file_name: Path to output file.
    :param num_wf_labels_matrix: M-by-N numpy array with number of WF labels at
        each grid cell.
    :param num_cf_labels_matrix: Same but for cold fronts.
    :param num_unique_wf_matrix: M-by-N numpy array with number of unique warm
        fronts at each grid cell.
    :param num_unique_cf_matrix: Same but for cold fronts.
    :param first_time_unix_sec: See doc for `find_gridded_count_file`.
    :param last_time_unix_sec: Same.
    :param prediction_file_names: 1-D list of paths to input files (readable by
        `prediction_io.read_file`).  This is metadata.
    :param separation_time_sec: Separation time (for more details, see doc for
        `apply_separation_time`).  This is metadata.
    :param hours: See doc for `find_gridded_count_file`.
    :param months: Same.
    """

    # Check input args.
    error_checking.assert_is_integer_numpy_array(num_wf_labels_matrix)
    error_checking.assert_is_geq_numpy_array(num_wf_labels_matrix, 0)
    error_checking.assert_is_numpy_array(
        num_wf_labels_matrix, num_dimensions=2)

    expected_dim = numpy.array(num_wf_labels_matrix.shape, dtype=int)

    error_checking.assert_is_integer_numpy_array(num_cf_labels_matrix)
    error_checking.assert_is_geq_numpy_array(num_cf_labels_matrix, 0)
    error_checking.assert_is_numpy_array(
        num_cf_labels_matrix, exact_dimensions=expected_dim)

    error_checking.assert_is_integer_numpy_array(num_unique_wf_matrix)
    error_checking.assert_is_geq_numpy_array(num_unique_wf_matrix, 0)
    error_checking.assert_is_numpy_array(
        num_unique_wf_matrix, exact_dimensions=expected_dim)

    error_checking.assert_is_integer_numpy_array(num_unique_cf_matrix)
    error_checking.assert_is_geq_numpy_array(num_unique_cf_matrix, 0)
    error_checking.assert_is_numpy_array(
        num_unique_cf_matrix, exact_dimensions=expected_dim)

    error_checking.assert_is_integer(first_time_unix_sec)
    error_checking.assert_is_integer(last_time_unix_sec)
    error_checking.assert_is_greater(last_time_unix_sec, first_time_unix_sec)

    error_checking.assert_is_string_list(prediction_file_names)
    error_checking.assert_is_numpy_array(
        numpy.array(prediction_file_names), num_dimensions=1
    )

    error_checking.assert_is_integer(separation_time_sec)
    error_checking.assert_is_greater(separation_time_sec, 0)

    if hours is None:
        hours = numpy.array([-2, -1], dtype=int)
    else:
        _check_hours(hours)

    if months is None:
        months = numpy.array([-1], dtype=int)
    else:
        _check_months(months)

    # Open file.
    file_system_utils.mkdir_recursive_if_necessary(file_name=netcdf_file_name)
    dataset_object = netCDF4.Dataset(
        netcdf_file_name, 'w', format='NETCDF3_64BIT_OFFSET')

    # Set global attributes and dimensions.
    dataset_object.setncattr(SEPARATION_TIME_KEY, separation_time_sec)
    dataset_object.setncattr(FIRST_TIME_KEY, first_time_unix_sec)
    dataset_object.setncattr(LAST_TIME_KEY, last_time_unix_sec)
    dataset_object.setncattr(HOURS_KEY, hours)
    dataset_object.setncattr(MONTHS_KEY, months)

    num_file_name_chars = max([
        len(f) for f in prediction_file_names
    ])

    dataset_object.createDimension(
        ROW_DIMENSION_KEY, num_wf_labels_matrix.shape[0]
    )
    dataset_object.createDimension(
        COLUMN_DIMENSION_KEY, num_wf_labels_matrix.shape[1]
    )
    dataset_object.createDimension(
        PREDICTION_FILE_DIM_KEY, len(prediction_file_names)
    )
    dataset_object.createDimension(
        PREDICTION_FILE_CHAR_DIM_KEY, num_file_name_chars
    )

    # Add variables.
    dataset_object.createVariable(
        NUM_WF_LABELS_KEY, datatype=numpy.int32,
        dimensions=(ROW_DIMENSION_KEY, COLUMN_DIMENSION_KEY)
    )
    dataset_object.variables[NUM_WF_LABELS_KEY][:] = num_wf_labels_matrix

    dataset_object.createVariable(
        NUM_CF_LABELS_KEY, datatype=numpy.int32,
        dimensions=(ROW_DIMENSION_KEY, COLUMN_DIMENSION_KEY)
    )
    dataset_object.variables[NUM_CF_LABELS_KEY][:] = num_cf_labels_matrix

    dataset_object.createVariable(
        NUM_UNIQUE_WF_KEY, datatype=numpy.int32,
        dimensions=(ROW_DIMENSION_KEY, COLUMN_DIMENSION_KEY)
    )
    dataset_object.variables[NUM_UNIQUE_WF_KEY][:] = num_unique_wf_matrix

    dataset_object.createVariable(
        NUM_UNIQUE_CF_KEY, datatype=numpy.int32,
        dimensions=(ROW_DIMENSION_KEY, COLUMN_DIMENSION_KEY)
    )
    dataset_object.variables[NUM_UNIQUE_CF_KEY][:] = num_unique_cf_matrix

    this_string_type = 'S{0:d}'.format(num_file_name_chars)
    file_names_char_array = netCDF4.stringtochar(numpy.array(
        prediction_file_names, dtype=this_string_type
    ))

    dataset_object.createVariable(
        PREDICTION_FILES_KEY, datatype='S1',
        dimensions=(PREDICTION_FILE_DIM_KEY, PREDICTION_FILE_CHAR_DIM_KEY)
    )
    dataset_object.variables[PREDICTION_FILES_KEY][:] = numpy.array(
        file_names_char_array)

    dataset_object.close()


def read_gridded_counts(netcdf_file_name):
    """Reads gridded front counts from NetCDF file.

    :param netcdf_file_name: Path to input file.
    :return: count_dict: Dictionary with the following keys.
    count_dict["num_wf_labels_matrix"]: See doc for `write_gridded_counts`.
    count_dict["num_cf_labels_matrix"]: Same.
    count_dict["num_unique_wf_matrix"]: Same.
    count_dict["num_unique_cf_matrix"]: Same.
    count_dict["first_time_unix_sec"]: Same.
    count_dict["last_time_unix_sec"]: Same.
    count_dict["hours"]: Same.
    count_dict["months"]: Same.
    count_dict["prediction_file_names"]: Same.
    count_dict["separation_time_sec"]: Same.
    """

    dataset_object = netCDF4.Dataset(netcdf_file_name)

    hours = getattr(dataset_object, HOURS_KEY)
    if isinstance(hours, numpy.ndarray):
        hours = hours.astype(int)
    else:
        hours = numpy.array([hours], dtype=int)

    if len(hours) == 1 and hours[0] == -1:
        hours = None

    months = getattr(dataset_object, MONTHS_KEY)
    if isinstance(months, numpy.ndarray):
        months = months.astype(int)
    else:
        months = numpy.array([months], dtype=int)

    if len(months) == 1 and months[0] == -1:
        months = None

    count_dict = {
        FIRST_TIME_KEY: int(getattr(dataset_object, FIRST_TIME_KEY)),
        LAST_TIME_KEY: int(getattr(dataset_object, LAST_TIME_KEY)),
        HOURS_KEY: hours,
        MONTHS_KEY: months,
        NUM_WF_LABELS_KEY: numpy.array(
            dataset_object.variables[NUM_WF_LABELS_KEY][:], dtype=int
        ),
        NUM_CF_LABELS_KEY: numpy.array(
            dataset_object.variables[NUM_CF_LABELS_KEY][:], dtype=int
        ),
        NUM_UNIQUE_WF_KEY: numpy.array(
            dataset_object.variables[NUM_UNIQUE_WF_KEY][:], dtype=int
        ),
        NUM_UNIQUE_CF_KEY: numpy.array(
            dataset_object.variables[NUM_UNIQUE_CF_KEY][:], dtype=int
        ),
        PREDICTION_FILES_KEY: [
            str(s) for s in
            netCDF4.chartostring(
                dataset_object.variables[PREDICTION_FILES_KEY][:]
            )
        ],
        SEPARATION_TIME_KEY: int(getattr(dataset_object, SEPARATION_TIME_KEY))
    }

    dataset_object.close()
    return count_dict