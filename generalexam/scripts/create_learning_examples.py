"""Creates example files.

--- NOTATION ---

The following letters will be used throughout this file.

E = number of learning examples
M = number of rows in predictor grid
N = number of columns in predictor grid
C = number of predictor variables
"""

import copy
import argparse
import numpy
from gewittergefahr.gg_utils import time_conversion
from gewittergefahr.gg_utils import time_periods
from gewittergefahr.gg_utils import error_checking
from generalexam.ge_io import predictor_io
from generalexam.ge_utils import predictor_utils
from generalexam.machine_learning import machine_learning_utils as ml_utils
from generalexam.machine_learning import learning_examples_io as examples_io

SEPARATOR_STRING = '\n\n' + '*' * 50 + '\n\n'

INPUT_TIME_FORMAT = '%Y%m%d%H'
TIME_INTERVAL_SECONDS = 10800

PREDICTOR_DIR_ARG_NAME = 'input_predictor_dir_name'
FIRST_TIME_ARG_NAME = 'first_time_string'
LAST_TIME_ARG_NAME = 'last_time_string'
PRESSURE_LEVEL_ARG_NAME = 'pressure_level_mb'
PREDICTOR_NAMES_ARG_NAME = 'predictor_names'
NUM_HALF_ROWS_ARG_NAME = 'num_half_rows'
NUM_HALF_COLUMNS_ARG_NAME = 'num_half_columns'
NORMALIZATION_TYPE_ARG_NAME = 'normalization_type_string'
CLASS_FRACTIONS_ARG_NAME = 'class_fractions'
FRONT_DIR_ARG_NAME = 'input_gridded_front_dir_name'
DILATION_DISTANCE_ARG_NAME = 'dilation_distance_metres'
MASK_FILE_ARG_NAME = 'input_mask_file_name'
MAX_EXAMPLES_PER_TIME_ARG_NAME = 'max_examples_per_time'
NUM_TIMES_PER_FILE_ARG_NAME = 'num_times_per_output_file'
OUTPUT_DIR_ARG_NAME = 'output_dir_name'

# TODO(thunderhoser): Need to keep metadata for normalization.
# TODO(thunderhoser): May want to allow different normalization.

PREDICTOR_DIR_HELP_STRING = (
    'Name of top-level directory with predictors.  Input files therein '
    'will be found by `predictor_io.find_file` and read by '
    '`predictor_io.read_file`.')

TIME_HELP_STRING = (
    'Time (format "yyyymmddHH").  This script will create learning examples for'
    ' all time steps in the period `{0:s}`...`{1:s}`.'
).format(FIRST_TIME_ARG_NAME, LAST_TIME_ARG_NAME)

PRESSURE_LEVEL_HELP_STRING = (
    'Will create examples only for this pressure level (millibars).  To use '
    'surface data as predictors, leave this argument alone.')

PREDICTOR_NAMES_HELP_STRING = (
    'Names of predictor variables.  Must be accepted by '
    '`predictor_utils.check_field_name`.')

NUM_HALF_ROWS_HELP_STRING = (
    'Number of rows in half-grid (on either side of center) for predictors.')

NUM_HALF_COLUMNS_HELP_STRING = (
    'Number of columns in half-grid (on either side of center) for predictors.')

NORMALIZATION_TYPE_HELP_STRING = (
    'Normalization type (must be accepted by '
    '`machine_learning_utils._check_normalization_type`).')

CLASS_FRACTIONS_HELP_STRING = (
    'Downsampling fractions for the 3 classes (no front, warm front, cold '
    'front).  Must sum to 1.0.')

FRONT_DIR_HELP_STRING = (
    'Name of top-level directory with gridded front labels.  Files therein will'
    ' be found by `fronts_io.find_gridded_file` and read by '
    '`fronts_io.read_grid_from_file`.')

DILATION_DISTANCE_HELP_STRING = (
    'Dilation distance for gridded warm-front and cold-front labels.')

MASK_FILE_HELP_STRING = (
    'Path to mask file (determines which grid cells can be used as center of '
    'learning example).  Will be read by '
    '`machine_learning_utils.read_narr_mask`.  If you do not want a mask, leave'
    ' this empty.')

MAX_EXAMPLES_PER_TIME_HELP_STRING = (
    'Max number of learning examples per time step.')

NUM_TIMES_PER_FILE_HELP_STRING = (
    'Number of time steps per output (example) file.')

OUTPUT_DIR_HELP_STRING = (
    'Name of output directory.  Learning examples will be written here by '
    '`learning_examples_io.write_file`, to exact locations determined by '
    '`learning_examples_io.find_file`.')

TOP_PREDICTOR_DIR_NAME_DEFAULT = '/condo/swatwork/ralager/era5_data/processed'
TOP_FRONT_DIR_NAME_DEFAULT = (
    '/condo/swatwork/ralager/fronts_netcdf/narr_grids_no_dilation')
DEFAULT_MASK_FILE_NAME = '/condo/swatwork/ralager/fronts_netcdf/era5_mask.p'

DEFAULT_PREDICTOR_NAMES = [
    predictor_utils.U_WIND_GRID_RELATIVE_NAME,
    predictor_utils.V_WIND_GRID_RELATIVE_NAME,
    predictor_utils.WET_BULB_THETA_NAME,
    predictor_utils.TEMPERATURE_NAME,
    predictor_utils.SPECIFIC_HUMIDITY_NAME,
    predictor_utils.HEIGHT_NAME
]

DEFAULT_CLASS_FRACTIONS = numpy.array([0.5, 0.25, 0.25])

INPUT_ARG_PARSER = argparse.ArgumentParser()
INPUT_ARG_PARSER.add_argument(
    '--' + PREDICTOR_DIR_ARG_NAME, type=str, required=False,
    default=TOP_PREDICTOR_DIR_NAME_DEFAULT, help=PREDICTOR_DIR_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + FIRST_TIME_ARG_NAME, type=str, required=True, help=TIME_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + LAST_TIME_ARG_NAME, type=str, required=True, help=TIME_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + PRESSURE_LEVEL_ARG_NAME, type=int, required=False,
    default=predictor_utils.DUMMY_SURFACE_PRESSURE_MB,
    help=PRESSURE_LEVEL_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + PREDICTOR_NAMES_ARG_NAME, type=str, nargs='+', required=False,
    default=DEFAULT_PREDICTOR_NAMES, help=PREDICTOR_NAMES_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + NUM_HALF_ROWS_ARG_NAME, type=int, required=False, default=16,
    help=NUM_HALF_ROWS_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + NUM_HALF_COLUMNS_ARG_NAME, type=int, required=False, default=16,
    help=NUM_HALF_COLUMNS_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + NORMALIZATION_TYPE_ARG_NAME, type=str, required=False,
    default=ml_utils.Z_SCORE_STRING, help=NORMALIZATION_TYPE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + CLASS_FRACTIONS_ARG_NAME, type=float, nargs=3, required=False,
    default=DEFAULT_CLASS_FRACTIONS, help=CLASS_FRACTIONS_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + FRONT_DIR_ARG_NAME, type=str, required=False,
    default=TOP_FRONT_DIR_NAME_DEFAULT, help=FRONT_DIR_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + DILATION_DISTANCE_ARG_NAME, type=float, required=False,
    default=50000, help=DILATION_DISTANCE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + MASK_FILE_ARG_NAME, type=str, required=False,
    default=DEFAULT_MASK_FILE_NAME, help=MASK_FILE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + MAX_EXAMPLES_PER_TIME_ARG_NAME, type=int, required=False,
    default=5000, help=MAX_EXAMPLES_PER_TIME_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + NUM_TIMES_PER_FILE_ARG_NAME, type=int, required=False, default=8,
    help=NUM_TIMES_PER_FILE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + OUTPUT_DIR_ARG_NAME, type=str, required=True,
    help=OUTPUT_DIR_HELP_STRING)


def _write_example_file(
        top_output_dir_name, example_dict, first_time_unix_sec,
        last_time_unix_sec):
    """Writes one set of learning examples to file.

    :param top_output_dir_name: See documentation at top of file.
    :param example_dict: Dictionary with keys documented in
        `learning_examples_io.create_examples`.
    :param first_time_unix_sec: First time in set.
    :param last_time_unix_sec: Last time in set.
    """

    if example_dict is None:
        return

    output_file_name = examples_io.find_file(
        top_directory_name=top_output_dir_name,
        first_valid_time_unix_sec=first_time_unix_sec,
        last_valid_time_unix_sec=last_time_unix_sec,
        raise_error_if_missing=False)

    print 'Writing examples to file: "{0:s}"...'.format(output_file_name)
    examples_io.write_file(netcdf_file_name=output_file_name,
                           example_dict=example_dict)


def _run(top_predictor_dir_name, first_time_string, last_time_string,
         pressure_level_mb, predictor_names, num_half_rows, num_half_columns,
         normalization_type_string, class_fractions, top_gridded_front_dir_name,
         dilation_distance_metres, mask_file_name, max_examples_per_time,
         num_times_per_output_file, top_output_dir_name):
    """Creates example files.

    This is effectively the main method.

    :param top_predictor_dir_name: See documentation at top of file.
    :param first_time_string: Same.
    :param last_time_string: Same.
    :param pressure_level_mb: Same.
    :param predictor_names: Same.
    :param num_half_rows: Same.
    :param num_half_columns: Same.
    :param normalization_type_string: Same.
    :param class_fractions: Same.
    :param top_gridded_front_dir_name: Same.
    :param dilation_distance_metres: Same.
    :param mask_file_name: Same.
    :param max_examples_per_time: Same.
    :param num_times_per_output_file: Same.
    :param top_output_dir_name: Same.
    """

    error_checking.assert_is_greater(num_times_per_output_file, 0)

    if mask_file_name in ['', 'None']:
        mask_file_name = None

    if pressure_level_mb == predictor_utils.DUMMY_SURFACE_PRESSURE_MB:
        predictor_names = [
            predictor_utils.PRESSURE_NAME
            if n == predictor_utils.HEIGHT_NAME else n
            for n in predictor_names
        ]
    else:
        predictor_names = [
            predictor_utils.HEIGHT_NAME
            if n == predictor_utils.PRESSURE_NAME else n
            for n in predictor_names
        ]

    if mask_file_name is not None:
        print 'Reading mask from: "{0:s}"...\n'.format(mask_file_name)
        mask_matrix = ml_utils.read_narr_mask(mask_file_name)[0]
    else:
        mask_matrix = None

    first_time_unix_sec = time_conversion.string_to_unix_sec(
        first_time_string, INPUT_TIME_FORMAT)
    last_time_unix_sec = time_conversion.string_to_unix_sec(
        last_time_string, INPUT_TIME_FORMAT)

    valid_times_unix_sec = time_periods.range_and_interval_to_list(
        start_time_unix_sec=first_time_unix_sec,
        end_time_unix_sec=last_time_unix_sec,
        time_interval_sec=TIME_INTERVAL_SECONDS, include_endpoint=True)

    this_example_dict = None
    this_first_time_unix_sec = valid_times_unix_sec[0]
    num_times = len(valid_times_unix_sec)

    for i in range(num_times):
        if numpy.mod(i, num_times_per_output_file) == 0 and i > 0:
            _write_example_file(
                top_output_dir_name=top_output_dir_name,
                example_dict=this_example_dict,
                first_time_unix_sec=this_first_time_unix_sec,
                last_time_unix_sec=valid_times_unix_sec[i - 1]
            )

            print SEPARATOR_STRING
            this_example_dict = None
            this_first_time_unix_sec = valid_times_unix_sec[i]

        this_new_example_dict = examples_io.create_examples(
            top_predictor_dir_name=top_predictor_dir_name,
            top_gridded_front_dir_name=top_gridded_front_dir_name,
            valid_time_unix_sec=valid_times_unix_sec[i],
            predictor_names=predictor_names,
            pressure_level_mb=pressure_level_mb,
            num_half_rows=num_half_rows, num_half_columns=num_half_columns,
            dilation_distance_metres=dilation_distance_metres,
            class_fractions=class_fractions,
            max_num_examples=max_examples_per_time,
            normalization_type_string=normalization_type_string,
            narr_mask_matrix=mask_matrix)

        print '\n'
        if this_new_example_dict is None:
            continue

        if this_example_dict is None:
            this_example_dict = copy.deepcopy(this_new_example_dict)
            continue

        for this_key in examples_io.MAIN_KEYS:
            this_example_dict[this_key] = numpy.concatenate(
                (this_example_dict[this_key], this_new_example_dict[this_key]),
                axis=0
            )

    _write_example_file(
        top_output_dir_name=top_output_dir_name,
        example_dict=this_example_dict,
        first_time_unix_sec=this_first_time_unix_sec,
        last_time_unix_sec=valid_times_unix_sec[-1]
    )


if __name__ == '__main__':
    INPUT_ARG_OBJECT = INPUT_ARG_PARSER.parse_args()

    _run(
        top_predictor_dir_name=getattr(INPUT_ARG_OBJECT, PREDICTOR_DIR_ARG_NAME),
        first_time_string=getattr(INPUT_ARG_OBJECT, FIRST_TIME_ARG_NAME),
        last_time_string=getattr(INPUT_ARG_OBJECT, LAST_TIME_ARG_NAME),
        pressure_level_mb=getattr(INPUT_ARG_OBJECT, PRESSURE_LEVEL_ARG_NAME),
        predictor_names=getattr(INPUT_ARG_OBJECT, PREDICTOR_NAMES_ARG_NAME),
        num_half_rows=getattr(INPUT_ARG_OBJECT, NUM_HALF_ROWS_ARG_NAME),
        num_half_columns=getattr(INPUT_ARG_OBJECT, NUM_HALF_COLUMNS_ARG_NAME),
        normalization_type_string=getattr(
            INPUT_ARG_OBJECT, NORMALIZATION_TYPE_ARG_NAME),
        class_fractions=numpy.array(getattr(
            INPUT_ARG_OBJECT, CLASS_FRACTIONS_ARG_NAME
        )),
        top_gridded_front_dir_name=getattr(
            INPUT_ARG_OBJECT, FRONT_DIR_ARG_NAME),
        dilation_distance_metres=getattr(
            INPUT_ARG_OBJECT, DILATION_DISTANCE_ARG_NAME),
        mask_file_name=getattr(INPUT_ARG_OBJECT, MASK_FILE_ARG_NAME),
        max_examples_per_time=getattr(
            INPUT_ARG_OBJECT, MAX_EXAMPLES_PER_TIME_ARG_NAME),
        num_times_per_output_file=getattr(
            INPUT_ARG_OBJECT, NUM_TIMES_PER_FILE_ARG_NAME),
        top_output_dir_name=getattr(INPUT_ARG_OBJECT, OUTPUT_DIR_ARG_NAME)
    )
