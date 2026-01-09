#!/bin/bash
# Wrapper to run ansible-playbook with macOS fork safety disabled
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
ansible-playbook "$@"
