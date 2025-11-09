# Working with Feature Branches

To create a local copy of a remote branch (for example, `miller`) so you can review
or build on the latest changes, follow the steps below from inside the repository
root:

1. **Fetch the latest branches and commits from the remote:**
   ```bash
   git fetch origin
   ```

2. **Create a local branch that tracks the remote branch:**
   ```bash
   git checkout -b miller origin/miller
   ```

   The `-b` flag creates a new local branch, and specifying `origin/miller`
   ensures the branch starts from the same commit as the remote reference.

3. **Verify the branch is tracking the remote counterpart (optional):**
   ```bash
   git status -sb
   ```
   The output should resemble `## miller...origin/miller`, confirming that the
   local branch is set to push and pull against `origin/miller`.

4. **Pull subsequent updates from the remote branch:**
   ```bash
   git pull
   ```
   When you are on the `miller` branch, this keeps your local copy in sync.

5. **Push any local commits back to the remote branch:**
   ```bash
   git push
   ```
   Git will automatically use the tracking relationship to push changes to
   `origin/miller`.

These steps provide a local working copy of the remote branch and keep it aligned
with the source of truth.
