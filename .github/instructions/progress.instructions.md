---
applyTo: '**'
---
# 📋 Progress Tracking & Session Management

## Development Session Workflow
For complex tasks requiring multiple steps, maintain structured progress tracking:

1. **Initialize Progress**: Start with a todo list outlining all tasks
2. **Progress Documentation**: Write current progress to `.github/copilot-progress.md` before starting work and read it when resuming tasks
3. **Branch-Specific Progress**: Each branch maintains its own progress in `.github/copilot-progress.md`
4. **Git Exclusion**: The progress file should not be committed to git branches to avoid merge conflicts
5. **Work One Task at a Time**: Mark one task as `in-progress` before starting work
6. **Milestone Commits**: For larger changes with new branches, commit at logical milestones with clear commit messages
7. **Update Progress**: Mark tasks as `completed` immediately after finishing
8. **User Checkpoints**: For multi-step tasks, include user validation points at key milestones
9. **Session Summary**: Provide clear status updates showing what's been accomplished

## Progress States
- **`not-started`**: Task not yet begun
- **`in-progress`**: Currently working on this task (limit to one at a time)
- **`completed`**: Task finished successfully

## Progress Update Format
When updating progress, use this structure:

**Current Status:**
- ✅ **Completed**: [Task description] - [Brief accomplishment]
- 🔄 **In Progress**: [Current task description] - [What's being worked on]
- ⏳ **Pending**: [Next task description] - [What's planned]

**Next Steps:**
- [Clear description of immediate next action]
- [Any blockers or dependencies]

## Communication Guidelines
- **User Feedback Integration**: Include user validation points at key milestones for complex tasks
- **Status Transparency**: Provide regular updates on progress and any encountered issues
- **Blocker Communication**: Immediately communicate any blockers or dependencies that require user input
- **Incremental Delivery**: For large features, deliver working increments for user feedback

## Commit Guidelines
- **Milestone Commits**: Break large changes into logical commits at task completion points
- **Clear Messages**: Use descriptive commit messages that explain what was implemented and why
- **Atomic Commits**: Each commit should contain related changes that work together
- **Test Before Commit**: Ensure code compiles and basic tests pass before committing