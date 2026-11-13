#!/bin/bash

if [[ -z "${FUZZITIZER_ROOT}" ]]; then

    export FUZZITIZER_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
    export IPFUZZ_ROOT="$FUZZITIZER_ROOT/ipfuzzer"

    export PATH=~/.local/bin:$PATH

    echo "FUZZItizer setup complete"

else

    echo "FUZZItizer setup already sourced!"

fi
