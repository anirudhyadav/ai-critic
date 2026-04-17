#!/usr/bin/env bash
# Source this file to get the @aicritic shell alias.
#
#   source /path/to/ai-critic/aicritic-init.sh
#
# Or add to your ~/.zshrc / ~/.bashrc:
#   source /path/to/ai-critic/aicritic-init.sh

# zsh supports @ in function names directly.
# bash requires a workaround via $FUNCNAME tricks — the function approach below
# works in both bash 4+ and zsh.

if [ -n "$ZSH_VERSION" ]; then
    # zsh: alias works cleanly
    alias '@aicritic'='aicritic'
else
    # bash: define a function (aliases with @ don't parse reliably in bash)
    function '@aicritic'() { aicritic "$@"; }
    export -f '@aicritic' 2>/dev/null || true
fi
