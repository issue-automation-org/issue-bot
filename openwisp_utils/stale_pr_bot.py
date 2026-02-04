#!/usr/bin/env python3
"""Stale PR Management Bot - Automated stale PR detection and management"""

import os
import time
from datetime import datetime, timezone, timedelta
from github import Github, GithubException


class StalePRBot:
    def __init__(self):
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self.repository_name = os.environ.get("REPOSITORY")
        self.DAYS_BEFORE_STALE_WARNING = 7
        self.DAYS_BEFORE_UNASSIGN = 14
        self.DAYS_BEFORE_CLOSE = 60
        if self.github_token and self.repository_name:
            try:
                self.github = Github(self.github_token)
                self.repo = self.github.get_repo(self.repository_name)
            except Exception as e:
                print(f"Warning: Could not initialize GitHub client: {e}")
                self.github = None
                self.repo = None
        else:
            missing = []
            if not self.github_token:
                missing.append("GITHUB_TOKEN")
            if not self.repository_name:
                missing.append("REPOSITORY")
            print(f"Warning: Missing environment variables: {', '.join(missing)}")
            self.github = None
            self.repo = None

    def get_days_since_activity(self, pr, last_changes_requested):
        """Calculate days since last contributor activity after changes requested"""
        if not last_changes_requested:
            return 0
            
        try:
            pr_author = pr.user.login
            last_author_activity = None
            commits = list(self.repo.get_commits(sha=pr.head.sha))
            for commit in commits:
                commit_date = commit.commit.author.date
                if commit_date > last_changes_requested:
                    if commit.author and commit.author.login == pr_author:
                        if not last_author_activity or commit_date > last_author_activity:
                            last_author_activity = commit_date
            
            comments = list(pr.get_issue_comments())
            for comment in comments:
                if comment.user.login == pr_author:
                    comment_date = comment.created_at
                    if comment_date > last_changes_requested:
                        if not last_author_activity or comment_date > last_author_activity:
                            last_author_activity = comment_date
            
            reference_date = last_author_activity or last_changes_requested
            now = datetime.now(timezone.utc)
            return (now - reference_date).days
            
        except Exception as e:
            print(f"Error calculating activity for PR #{pr.number}: {e}")
            return 0

    def get_last_changes_requested(self, pr):
        """Get the date of the most recent 'changes_requested' review"""
        try:
            reviews = list(pr.get_reviews())
            changes_requested_reviews = [
                r for r in reviews 
                if r.state == 'CHANGES_REQUESTED'
            ]
            
            if not changes_requested_reviews:
                return None
                
            # Sort by submission date and get the most recent
            changes_requested_reviews.sort(key=lambda r: r.submitted_at, reverse=True)
            return changes_requested_reviews[0].submitted_at
            
        except Exception as e:
            print(f"Error getting reviews for PR #{pr.number}: {e}")
            return None

    def has_bot_comment(self, pr, comment_type):
        """Check if PR already has a specific type of bot comment"""
        try:
            comments = list(pr.get_issue_comments())
            for comment in comments:
                if comment.user.type == 'Bot' and comment_type.lower() in comment.body.lower():
                    return True
            return False
        except Exception:
            return False

    def extract_linked_issues(self, pr_body):
        """Extract issue numbers from PR body"""
        import re
        if not pr_body:
            return []
        issue_pattern = r'(?:fix(?:es)?|close[sd]?|resolve[sd]?)\s+#(\d+)'
        matches = re.findall(issue_pattern, pr_body, re.IGNORECASE)
        return list(set(int(match) for match in matches))

    def unassign_linked_issues(self, pr):
        """Unassign linked issues from PR author"""
        try:
            linked_issues = self.extract_linked_issues(pr.body or '')
            pr_author = pr.user.login
            unassigned_count = 0
            
            for issue_number in linked_issues:
                try:
                    issue = self.repo.get_issue(issue_number)
                    
                    if issue.pull_request:
                        continue
                    assignees = [assignee.login for assignee in issue.assignees]
                    if pr_author in assignees:
                        issue.remove_from_assignees(pr_author)
                        unassigned_count += 1
                        print(f'Unassigned {pr_author} from issue #{issue_number}')
                        
                except Exception as e:
                    print(f'Error unassigning issue #{issue_number}: {e}')
                    
            return unassigned_count
            
        except Exception as e:
            print(f'Error processing linked issues for PR #{pr.number}: {e}')
            return 0

    def close_stale_pr(self, pr, days_inactive):
        """Close PR after extended inactivity"""
        try:
            pr_author = pr.user.login
            
            close_message = f"""Hi @{pr_author} 👋,

This pull request has been automatically closed due to **{days_inactive} days of inactivity** after changes were requested.

We understand that life gets busy, and we appreciate your initial contribution! 💙

**The door is always open** for you to come back:
- You can **reopen this PR** at any time if you'd like to continue working on it
- Feel free to push new commits addressing the requested changes
- If you reopen the PR, the linked issue will be reassigned to you

If you have any questions or need help, don't hesitate to reach out. We're here to support you!

Thank you for your interest in contributing to OpenWISP! 🙏"""

            pr.create_issue_comment(close_message)
            pr.edit(state='closed')
            
            # Unassign linked issues
            unassigned_count = self.unassign_linked_issues(pr)
            print(f"Closed PR #{pr.number} after {days_inactive} days of inactivity, unassigned {unassigned_count} issues")
            
            return True
            
        except Exception as e:
            print(f"Error closing PR #{pr.number}: {e}")
            return False

    def mark_pr_stale(self, pr, days_inactive):
        """Mark PR as stale after moderate inactivity"""
        try:
            pr_author = pr.user.login
            
            unassign_message = f"""Hi @{pr_author} 👋,

This pull request has been marked as **stale** due to **{days_inactive} days of inactivity** after changes were requested.

As a result, **the linked issue(s) have been unassigned** from you to allow other contributors to work on it.

However, **you can still continue working on this PR**! If you push new commits or respond to the review feedback:
- The issue will be reassigned to you
- Your contribution is still very welcome

If you need more time or have questions about the requested changes, please let us know. We're happy to help! 🤝

If there's no further activity within **{self.DAYS_BEFORE_CLOSE - days_inactive} more days**, this PR will be automatically closed (but can be reopened anytime)."""

            pr.create_issue_comment(unassign_message)
            
            unassigned_count = self.unassign_linked_issues(pr)
            try:
                pr.add_to_labels('stale')
            except Exception as e:
                print(f"Could not add stale label: {e}")
                
            print(f"Marked PR #{pr.number} as stale after {days_inactive} days, unassigned {unassigned_count} issues")
            return True
            
        except Exception as e:
            print(f"Error marking PR #{pr.number} as stale: {e}")
            return False

    def send_stale_warning(self, pr, days_inactive):
        """Send warning about upcoming stale status"""
        try:
            pr_author = pr.user.login
            
            warning_message = f"""Hi @{pr_author} 👋,

This is a friendly reminder that this pull request has had **no activity for {days_inactive} days** since changes were requested.

We'd love to see this contribution merged! Please take a moment to:
- Address the review feedback
- Push your changes
- Let us know if you have any questions or need clarification

If you're busy or need more time, no worries! Just leave a comment to let us know you're still working on it.

**Note:** If there's no activity within **{self.DAYS_BEFORE_UNASSIGN - days_inactive} more days**, the linked issue will be unassigned to allow other contributors to work on it.

Thank you for your contribution! 🙏"""

            pr.create_issue_comment(warning_message)
            print(f"Sent stale warning for PR #{pr.number}")
            return True
            
        except Exception as e:
            print(f"Error sending warning for PR #{pr.number}: {e}")
            return False

    def process_stale_prs(self):
        """Process all open PRs for stale management"""
        if not self.repo:
            print("GitHub repository not initialized")
            return
            
        try:
            open_prs = list(self.repo.get_pulls(state='open'))
            print(f"Found {len(open_prs)} open pull requests")
            
            processed_count = 0
            
            for pr in open_prs:
                try:
                    # Check if changes were requested
                    last_changes_requested = self.get_last_changes_requested(pr)
                    if not last_changes_requested:
                        # No changes requested, PR is waiting for review - not stale
                        continue
                        
                    days_inactive = self.get_days_since_activity(pr, last_changes_requested)
                    print(f"PR #{pr.number}: {days_inactive} days since contributor activity")
                    
                    # Process based on inactivity period
                    if days_inactive >= self.DAYS_BEFORE_CLOSE:
                        if self.close_stale_pr(pr, days_inactive):
                            processed_count += 1
                            
                    elif days_inactive >= self.DAYS_BEFORE_UNASSIGN:
                        if not self.has_bot_comment(pr, 'stale') and not self.has_bot_comment(pr, 'unassigned'):
                            if self.mark_pr_stale(pr, days_inactive):
                                processed_count += 1
                                
                    elif days_inactive >= self.DAYS_BEFORE_STALE_WARNING:
                        if not self.has_bot_comment(pr, 'reminder') and not self.has_bot_comment(pr, 'stale warning'):
                            if self.send_stale_warning(pr, days_inactive):
                                processed_count += 1
                                
                    # Rate limiting - small delay between PR processing
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"Error processing PR #{pr.number}: {e}")
                    continue
                    
            print(f"Processed {processed_count} stale PRs")
            
        except Exception as e:
            print(f"Error in process_stale_prs: {e}")

    def run(self):
        """Main execution flow"""
        if not self.github or not self.repo:
            print("GitHub client not properly initialized, cannot proceed")
            return False
            
        print("Stale PR Management Bot starting...")
        
        try:
            self.process_stale_prs()
            return True
        except Exception as e:
            print(f"Error in main execution: {e}")
            return False
        finally:
            print("Stale PR Management Bot completed")


if __name__ == "__main__":
    bot = StalePRBot()
    bot.run()