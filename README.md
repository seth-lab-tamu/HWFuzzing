# HW_Fuzzing
The repository includes hardware fuzzing techniques developed in the SETH lab: [TheHuzz](https://www.usenix.org/conference/usenixsecurity22/presentation/kande), [HyPFuzz](https://www.usenix.org/system/files/usenixsecurity23-chen-chen.pdf), and [ReFuzz](https://arxiv.org/pdf/2512.04436).

#### Maintained by [Chen Chen](https://www.chenc.contact/), [Rahul Kande](https://www.rahulkande.com/), [Zeina AbuGhosh](https://www.linkedin.com/in/zeina-abughosh/), [Ted Hong](https://github.com/squishycat92).

## Getting Started


## Setup and Install Chipyard v1.13.0 (BOOMV4)
### 1. Install Required Python Packages
python3 -m venv hwfuzzing \
source ./hwfuzzing/bin/activate \
pip3 install gdown openpyxl tqdm pandas numpy matplotlib jsonlines

### 2. Source the setup script for Chipyard 1.13.0:
update paths in thehuzz_setup.sh \
source thehuzz_setup.sh

### 3. Install Chipyard Toolchain and Dependencies
# install prerequisites for chipyard 1130 (1 min)
./setup_scripts/install_chipyard_1130_tools.sh

# install chipyard 1.13.0 (20 mins, 10 mins)
./setup_scripts/install_chipyard_1130_pt1.sh\
./setup_scripts/install_chipyard_1130_pt2.sh

### 4. re-source the environment:
source thehuzz_setup.sh

### Setup Benchmarks
Benchmarks currently supported: **Rocket Core**, **CVA6**, **BOOMV3**, and **BOOMV4** processors from the [Chipyard SoC](https://chipyard.readthedocs.io/en/1.13.0/) framework (v1.13.0).

### 5. Install BoomV3:
./setup_scripts/install_boom_v3.sh

### 5. Install BoomV4:
./setup_scripts/install_boom_v4.sh

### 5. Install Rocket Core:
./setup_scripts/install_rc.sh

### 5. Install CVA6:
./setup_scripts/install_cva6.sh


### Running TheHuzz on BoomV4:

- `source thehuzz_setup.sh #Make sure you do this every time in the root directory!`
- `python3 fuzz.py -co boomv4 -j <no threads> -mp <max testcases>`
  - Ex: `python3 fuzz.py -co boomv4 -j 10 -mp 30`
  - Use `python3 fuzz.py --help for details about more arguments`
  - Important arguments:
    - `python3 fuzz.py -co <benchmark> -id <run name> -mp <max testcases> -sj <simulation batch size> -j <num threads to use>`


### HyPFuzz (On Progress)


### ReFuzz (On Progress)



## Publication
BibTeX to cite TheHuzz:
```
@article{kande2022thehuzz,
  title={{TheHuzz: Instruction Fuzzing of Processors Using Golden-Reference Models for Finding Software-Exploitable Vulnerabilities}},
  author={Kande, Rahul and Crump, Addison and Persyn, Garrett and Jauernig, Patrick and Sadeghi, Ahmad-Reza and Tyagi, Aakash and Rajendran, Jeyavijayan},
  booktitle={31st USENIX Security Symposium},
  pages={3219--3236},
  year={2022}
}
```
BibTeX to cite HyPFuzz:
```
@article{chen2023hypfuzz,
  title={{HyPFuzz: Formal-Assisted Processor Fuzzing}},
  author={Chen, Chen and Kande, Rahul and Nguyen, Nathan and Andersen, Flemming and Tyagi, Aakash and Sadeghi, Ahmad-Reza and Rajendran, Jeyavijayan},
  booktitle={32nd USENIX Security Symposium},
  pages={1361--1378},
  year={2023}
}
```
BibTeX to cite ReFuzz:
```
@article{chen2025refuzz,
  title={{ReFuzz: Reusing Tests for Processor Fuzzing with Contextual Bandits}},
  author={Chen, Chen and Xu, Zaiyan and Rostami, Mohamadreza and Liu, David and Kalathil, Dileep and Sadeghi, Ahmad-Reza and Rajendran, Jeyavijayan},
  journal={arXiv preprint arXiv:2512.04436},
  year={2025}
}
```
