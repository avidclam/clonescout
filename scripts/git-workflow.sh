# git-workflow.sh — Shell helpers for the issue-based git workflow (issue-start, issue-status, issue-finish).
#
# This file must be sourced, not executed directly.
# See docs/developer-guide.md for setup instructions.
#
# Usage: source scripts/git-workflow.sh
[[ "${BASH_SOURCE[0]}" == "${0}" ]] && echo "Error: source this file, don't run it directly." && exit 1

# 1. Start working on an issue (create branch + GitHub Issue)
function issue-start() {
    if [ -z "$1" ]; then
        echo "❌ Error: Specify the filename without extension (e.g., issue-start 0001-cli-config)"
        return 1
    fi

    local slug=$1
    local file="issues/${slug}.md"

    if [ ! -f "$file" ]; then
        echo "❌ Error: File $file not found!"
        return 1
    fi

    # Extract title: strip leading/trailing **, strip leading #·, trim surrounding quotes, strip backticks
    local title=$(head -n 1 "$file" | sed -E 's/^\*\*//; s/\*\*$//; s/^#+[[:space:]]*//; s/^"(.*)"$/\1/; s/`//g')

    echo "🚀 Creating local branch feature/$slug..."
    git checkout -b "feature/$slug" || {
        echo "❌ Failed to create branch feature/$slug"
        return 1
    }

    echo "📝 Creating GitHub Issue: \"$title\"..."
    local gh_output
    gh_output=$(gh issue create --title "$title" --body-file "$file") || {
        echo "❌ Failed to create GitHub Issue. Rolling back branch..."
        git checkout main
        git branch -D "feature/$slug" 2>/dev/null
        return 1
    }

    # Extract the issue number from the GitHub CLI output URL
    local issue_num=$(echo "$gh_output" | grep -oE '[0-9]+$')

    if [ -n "$issue_num" ]; then
        git config "branch.feature/${slug}.gh-issue-num" "$issue_num"
        echo "✅ Issue #$issue_num created, branch feature/$slug ready."
        echo ""
        echo "Next steps:"
        echo "  1. Implement the feature"
        echo "  2. Run: issue-finish"
    else
        echo "⚠️  Branch created but could not determine Issue number."
        echo "   Set it manually:"
        echo "     git config 'branch.feature/${slug}.gh-issue-num' <NUMBER>"
    fi
}

# 2. Show current issue-branch status
function issue-status() {
    local branch=$(git branch --show-current)

    if [[ ! "$branch" =~ ^feature/ ]]; then
        echo "ℹ️  Not on a feature branch (current: $branch)"
        return 0
    fi

    local slug=${branch#feature/}
    local file="issues/${slug}.md"
    local issue_num=$(git config "branch.${branch}.gh-issue-num")

    echo "🔍 Current branch: $branch"
    echo "   Issue file:     ${file} $([ -f "$file" ] && echo '✅' || echo '❌ not found')"
    echo "   GitHub Issue:   ${issue_num:+#$issue_num}${issue_num:-⚠️  not set}"
    echo ""
    echo "📦 Working tree status:"
    git status --short
    echo ""
    echo "📊 Commits ahead of main:"
    git log main..HEAD --oneline 2>/dev/null || echo "   (none)"
}

# 3. Finish working, squash-merge locally, push main, delete branch
function issue-finish() {
    local branch=$(git branch --show-current)

    if [[ ! "$branch" =~ ^feature/ ]]; then
        echo "❌ Error: You are not on a feature/* branch (current: $branch)"
        return 1
    fi

    local slug=${branch#feature/}
    local file="issues/${slug}.md"

    if [ ! -f "$file" ]; then
        echo "❌ Error: Description file $file not found."
        return 1
    fi

    # Extract title (same logic as issue-start)
    local title=$(head -n 1 "$file" | sed -E 's/^\*\*//; s/\*\*$//; s/^#+[[:space:]]*//; s/^"(.*)"$/\1/; s/`//g')

    # Resolve GitHub Issue number
    local issue_num=$(git config "branch.${branch}.gh-issue-num")
    if [ -z "$issue_num" ]; then
        echo "⚠️  Issue number not found in git config. Searching via gh CLI..."
        issue_num=$(gh issue list --search "\"$title\"" --json number --jq '.[0].number' 2>/dev/null)
    fi
    if [ -z "$issue_num" ] || [ "$issue_num" = "null" ]; then
        echo "❌ Error: Could not determine GitHub Issue number."
        echo "   Set it manually and retry:"
        echo "     git config 'branch.${branch}.gh-issue-num' <NUMBER>"
        return 1
    fi

    echo "📋 Summary:"
    echo "   Branch:  $branch"
    echo "   Issue:   #$issue_num"
    echo "   Title:   $title"
    echo ""

    # Show status BEFORE staging so user can review
    echo "📦 Current changes in working tree:"
    git status
    echo "------------------------------------------------------"
    read -p "Press [Enter] to stage all, squash-merge into main and push (Ctrl+C to abort)..."

    # Stage and commit on feature branch — required for git merge --squash to work
    git add . || return 1

    # Check if there's anything to commit
    if git diff --cached --quiet; then
        # Nothing staged — check if there are commits ahead of main
        if [ -z "$(git log main..HEAD --oneline 2>/dev/null)" ]; then
            echo "❌ Nothing to commit and no commits ahead of main. Nothing to merge."
            return 1
        fi
        echo "ℹ️  No new changes to stage, but branch has commits ahead of main. Proceeding..."
    else
        git commit -m "WIP: ${title}" || {
            echo "❌ Commit failed on feature branch."
            return 1
        }
    fi

    # Switch to main and pull latest to avoid push rejection
    echo "🔀 Switching to main..."
    git checkout main || {
        echo "❌ Failed to switch to main."
        return 1
    }

    echo "⬇️  Pulling latest main from remote..."
    git pull --ff-only origin main || {
        echo "❌ Main has diverged from remote. Resolve manually."
        echo "   You can return to your branch: git checkout $branch"
        return 1
    }

    # Squash merge
    echo "🔀 Squash-merging $branch into main..."
    git merge --squash "$branch" || {
        echo "❌ Merge conflict! Resolve conflicts, then run:"
        echo "     git commit -m '${title} (Closes #${issue_num})'"
        echo "     git push origin main"
        echo "     git branch -D $branch"
        return 1
    }

    # The single definitive commit on main
    git commit -m "${title} (Closes #${issue_num})" || {
        echo "❌ Commit on main failed."
        return 1
    }

    # Push to remote
    echo "🚀 Pushing main to remote..."
    git push origin main || {
        echo "❌ Push failed! Your commit is on local main."
        echo "   Resolve and push manually: git push origin main"
        echo "   Then clean up: git branch -D $branch"
        return 1
    }

    # Explicitly close the issue via GitHub API (belt and suspenders)
    echo "🔒 Closing GitHub Issue #$issue_num..."
    gh issue close "$issue_num" --comment "Merged via squash commit on main." 2>/dev/null || {
        echo "⚠️  Could not close issue via API (will be closed by commit message on GitHub)."
    }

    # Clean up: remove git config and delete feature branch
    echo "🧹 Cleaning up..."
    git config --unset "branch.${branch}.gh-issue-num" 2>/dev/null
    git branch -D "$branch"

    echo ""
    echo "🎉 Done! Issue #$issue_num is closed and merged into main."
}
