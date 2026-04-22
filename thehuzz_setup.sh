#!/bin/bash

# only run the source if any of the setup files is not already sourced
if [[ -z "${THEHUZZ_ROOT}" || -z "${CHIPYARD_TOOLS_SOURCED}" || -z "${CHIPYARD_TOOLCHAIN_SOURCED}" ]]; then

    # fuzzer path (update this with your path)
    export THEHUZZ_ROOT="PATH_TO/HW_Fuzzing"

    # add project directories to python path
    export PYTHONPATH=$PYTHONPATH:$THEHUZZ_ROOT
    export PYTHONPATH=$PYTHONPATH:$THEHUZZ_ROOT/thehuzz
    export PYTHONPATH=$PYTHONPATH:$THEHUZZ_ROOT/utils
    export PYTHONPATH=$PYTHONPATH:$THEHUZZ_ROOT/benchmarks
    export PYTHONWARNINGS=ignore # disable syntax warning when using riscv to hex script

    # path for local installations
    export PATH=~/.local/bin:$PATH

    # setup vcs simulator
    source # include vcs simulator in your path

    # source setup file of tools required for chipyard
    CHIPYARD_TOOLS_SETUP_FILE=$THEHUZZ_ROOT/tools/chipyard_1130_tools_setup.sh
    source $CHIPYARD_TOOLS_SETUP_FILE
    CHIPYARD_SETUP_FILE=$THEHUZZ_ROOT/benchmarks/chipyard_1130/env.sh

    # source setup file of chipyard if chipyard is installed
    if [ -f "$CHIPYARD_SETUP_FILE" ];  then
        source $CHIPYARD_SETUP_FILE
    fi

    echo "HW Fuzzing setup complete"

else

    echo "HW Fuzzing setup already sourced!"

fi
