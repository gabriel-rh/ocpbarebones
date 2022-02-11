_aura_completion() {
    COMPREPLY=( $( COMP_WORDS="${COMP_WORDS[*]}" \
                   COMP_CWORD=$COMP_CWORD \
                   _AURA_COMPLETE=complete $1 ) )
    return 0
}

complete -F _aura_completion -o default aura;
