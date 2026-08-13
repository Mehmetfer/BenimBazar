# RBAC ACCEPTANCE

| Check | Status | Expect | Pass |
|-------|--------|--------|------|
| anon_dashboard | 401 | 401 | PASS |
| user_dashboard | 403 | 403 | PASS |
| user_self_escalate | 403 | 403 | PASS |
| admin_assign_superadmin | 403 | 403_or_400 | PASS |
| security_headers | 200 | nosniff+frame+csp | PASS |
