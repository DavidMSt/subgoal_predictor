# What this repo is about

This repository contains the software developed for my Master’s thesis Consensus through Learning: Graph Neural Networks for Task Allocation under Motion Constraints.
The work extends the existing BilboLab robotics framework with learning-based modules for decentralized task assignment and coordination in multi-robot systems.

# Contribution Overview

This fork adds the components required for learning-enhanced control, including:
- GNN-based decentralized task assignment
- kinodynamic motion-planning modules
- execution interfaces for integrating learned sub-goals
- supporting infrastructure (containers, scheduling, collision checking, etc.)

All thesis-related development is located under:
testbed/simulation/RobotManager/master_thesis/

# Notes

This is an active development repository containing all modules implemented as part of the thesis.

# How to run

1.	Install Python dependencies (pip install -r requirements.txt).
2.	Install OMPL manually if motion-planning components are used.
3.	For visualization, install frontend assets (npm install in the visualization directory).
4.	To launch the GUI, run: ``` python3 master_thesis/gui/thesis_gui.py ```
