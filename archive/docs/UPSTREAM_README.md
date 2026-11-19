# 654321
# SimpleLLM & SAST Blackboard

This repository contains a **scientific programming prototype** used to explore two main concepts:

1. **SimpleLLM Architecture** – a minimalistic framework for semantic typing.
2. **SAST Blackboard** – A multi-agent approach for semantic typing with focus of decision understanding via signals.

The goal of this project is to provide a clean and modifiable structure for testing, benchmarking, and extending LLM-driven analysis workflows.

---

## Project Structure



---

## Environment Setup

Create in Root folder if this project a new folder named "env", in which you must create a file named **`.env`** containing:
OPENAIKEY="your api key here"


This environment variable is required for all LLM-based components.

> **Note:**  
> Other parameters which will be used for both architectures (Sample IDs, historical references etc.) are located in `main.py` and can be modified easily.

---

## Running the Code

1. Make sure you have Python ≥ 3.10 installed.
2. Install the dependencies (requirements.txt):
3. Ensure that `env/.env` exists and contains your API key.
4. Start the program with the main.py in the root folder:

## Other Information
Within the main.py in the root folder are the main calls for the architectures SimpleLLM and the Blackboard.
Both will be given the same Sample IDs (SIDs) and historical references ID (HIDs) and other parameters.
Regarding the HIDs: If an architecture tries to process a SID which is in identical HIDs, this specific hid will not be utilized for this Sample, 

Each architecture generates by default in the given export path a new subfolder with the current timestamp.
Within this timestamp folder will be subfolder created for each SID which was processed, with the results for this specific SID.
If the parameter "evaluation run" like currently is set to true when invoking an architecture, other subfolders within the timestamp folder beside the SIDS will be created,
which hold global evaluations over all SIDs, and other specialized evaluations.

For each architecture folder exist a subfolder codebase with contains all relevant code for running the specific code,
while the main runner (a single python here) for the architecture can be found in the core subfolder under codebase.

Within the main runner may be other config parameters, like for the Blackboard Architecture which Chat-GPT should be used.