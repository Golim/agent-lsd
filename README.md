# AgentLSD: Evaluating AI Security Agents Under Adversarial Task Contamination

This repository contains the code for the paper "AgentLSD: Evaluating AI Security Agents Under Adversarial Task Contamination", published at the [19th ACM Workshop on Artificial Intelligence and Security](https://aisec.cc/).

## Repository Contents

### `framework/`

This directory contains the implementation of AgentLSD, a controlled framework for studying adversarial task contamination in agents solving CTF challenges.

Refer to the [README.md](framework/README.md) for setup and usage instructions.

#### Traps

`framework/deceptions/` contains the traps used in our experiments. Each trap is described as a YAML primitive and can be instantiated using the `framework/tools/generate_instances.py` script.

### `experiments/`

This directory contains the implementation of the CTF challenges and the evaluation of AgentLSD.

[README.md](experiments/README.md) provides instructions on how to download the scripts to run the experiments and the raw data.

#### CTF Challenges

`experiments/challenges/` contains the CTF challenges used in the experiments. Each challenge is implemented as a Python Flask application and can be augmented with traps to study the effects of adversarial task contamination.

Refer to the [README.md](experiments/challenges/README.md) for instructions on how to run the challenges and traps.
