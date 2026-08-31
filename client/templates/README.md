# {{CLIENT_NAME}}

AGK client organization: `{{CLIENT_ID}}`.

- Runtime: `{{RUNTIME_TYPE}}`
- Hermes profile: `{{HERMES_PROFILE}}`
- Secrets: `~/.config/agk/clients/{{CLIENT_ID}}/env`
- Standard: `../../system/CLIENT-STANDARD.md`

Before acting:

```bash
agk client doctor {{CLIENT_ID}}
eval "$(agk client env {{CLIENT_ID}})"
```

Work starts only from a Linear issue. Production requires an engineering
approval and a separate deployment authorization.

An authenticated owner message `fix it all from linear` authorizes all ready,
non-production issues in one batch. Run `agk client work
authorize-linear-batch {{CLIENT_ID}} --channel-id CHANNEL --message-id MESSAGE`.
The controller creates one Discord thread and one signed receipt per issue.
Never ask for repetitive `START ISSUE-ID` messages after a valid batch command;
production, spend, deletion, external access and secrets remain separate gates.
