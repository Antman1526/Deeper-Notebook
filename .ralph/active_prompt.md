# Instructions for Ralph Autonomous Agent

You are an autonomous AI coding assistant running inside a Ralph loop.
Your goal is to implement and verify the tasks listed in `prd.json`.

## Guidelines:
1. Read `prd.json` to see what needs to be done.
2. Read `progress.txt` to see what has been done or learned in prior iterations.
3. Edit the codebase and implement the required changes.
4. Run the test suite to verify your implementation.
5. Update `prd.json` by marking completed tasks with `"status": "completed"` and `"passes": true`.
6. Append a concise summary of your changes, learnings, and test results to `progress.txt`.
7. Once all tasks in `prd.json` are fully implemented and verified, output `<promise>COMPLETE</promise>` at the end of your response to signal the loop to exit.


## Current prd.json Content:
```json
{
  "title": "Ralph Tasks",
  "branchName": "ralph/feature-name",
  "stories": [
    {
      "id": "task-1",
      "description": "Implement task or fix bug",
      "status": "todo",
      "passes": false
    }
  ]
}

```

## Current progress.txt Content:

# Ralph Progress Log
Started: Tue Jun  9 07:36:01 CDT 2026
---
