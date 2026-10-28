# Try Operations → Quality → Delivery

**27 October layout update:** Open the **Review** ribbon (or **Home → Review and send**) before using Incoming leads, assignment, stage changes or push actions in the steps below. The record selector is now **Records**; column layouts use **Column view**. Worksheet tabs are at the bottom, and transfer history is under **Review → Notes and history**. The dummy accounts and workflow are unchanged. See [EXCEL_WORKSPACE_GUIDE.md](EXCEL_WORKSPACE_GUIDE.md).

Open **Start Lead Workspace.vbs**. Use `http://127.0.0.1:8765` on this PC. The six demo passwords are in the private local file **Data/LeadManager/demo-accounts.txt**; they are not embedded in source code or this guide. Each account is assigned only to **DEMO-FLOW — DEMO · Operations → Quality → Delivery**. Sign out and reopen the launcher to try another role, or open another instance for the next department.

| Username | Role | What to try |
|---|---|---|
| `demo.ops.lead` | Operations Team Lead | Approve selected team leads and Push to Quality |
| `demo.ops.employee` | Operations Employee | Private draft, validate/commit, submit for review |
| `demo.quality.lead` | Quality Team Lead | Receive, assign reviewers, Push to Delivery |
| `demo.quality.employee` | Quality Employee | Review assigned leads and record the quality outcome |
| `demo.delivery.lead` | Delivery Team Lead | Receive, assign delivery staff and approve delivery |
| `demo.delivery.employee` | Delivery Employee | View assigned work and mark approved leads Delivered |

All contacts are fictional, use example.com email addresses, and are labelled DEMO. Do not contact them. Existing campaigns and accounts are not assigned to these demo users. Quality and Delivery cannot open Scraper under the default module policy. The demo roles have no Administration access.

## Quick selected-lead handoff

1. Sign in as **demo.ops.lead**. The workspace opens **Records: My department**, with the **Workflow** column view. **Demo 01, Demo 02 and Demo 03** are already Approved. Click Demo 01's row number. Use Ctrl-click to select additional rows if wanted.
2. Open **Review** and click **Push to Quality**. The preview lists exactly the selected leads, their stage and any blocker. Add a note if needed and confirm. Only your selection is sent; other rows remain in Operations.
3. Sign in as **demo.quality.lead**. Open **Review → Incoming leads**. This changes the same table's Records filter. Select the received lead and click **Assign selected**. Choose **DEMO · Quality Employee**, confirm, then choose **Manual** assignment.
4. Sign in as **demo.quality.employee**. Select the assigned lead. Use **Review / change stage → Start quality review**, inspect the record, then **Review / change stage → Mark quality qualified**. The employee performs the review; the department lead performs the handoff.
5. Sign in as **demo.quality.lead**, select that **Quality Qualified** lead in **My department**, and click **Push to Delivery**. Review and confirm the selected-row preview.
6. Sign in as **demo.delivery.lead**. Click **Incoming leads**, select the received lead and **Assign selected** to **DEMO · Delivery Employee**. As the lead, use **Review / change stage → Approve delivery** after checking it.
7. Sign in as **demo.delivery.employee**. Select the approved lead and use **Review / change stage → Mark delivered** when delivery is complete.

**Review → View History** and **Notes and history → Transfer history** show the same Lead ID throughout the handoffs. Original ownership remains with the Operations employee. A sender can follow permitted transfers using **Records: Transferred leads**, but cannot change another department's current work. Incoming leads remain unassigned until the receiving supervisor assigns them; employees do not see another employee's assigned work.

## Other prepared examples

These are the initial states; they change as you practise:

| Sample records | Initial state | Next action |
|---|---|---|
| Demo 01–03 | Operations / Approved | Push to Quality |
| Demo 04–05 | Operations / Pending Team Lead Review | Operations lead: Review / change stage → Approve selected, then push |
| Demo 06–07 | Quality / Quality Qualified | Quality lead: Push to Delivery |
| Demo 08–09 | Delivery / unassigned incoming | Delivery lead: Incoming leads → Assign selected |
| Demo 10 | Delivered | Inspect history and dashboard counts |
| Demo 11–12 | Operations employee's private practice draft | Records: Working drafts → validate, commit, then submit committed rows for review |

Try selecting **Demo 01 and Demo 04 together before approving Demo 04**. The preview explains that Demo 04 still needs approval and disables Send. The service does not silently transfer a partial batch. A stale row version, changed campaign rule or revoked permission is checked again when sending.

**My department** shows current department work within the signed-in supervisor's existing team/campaign scope. **All permitted leads** also includes permitted transferred records. **Incoming transfers** shows actual unassigned handoffs; **Awaiting assignment** additionally includes other unassigned records. These are filters in one Lead Workspace, not separate pages.

## Manage the demonstration

Use your existing Super User account in **Administration → Users** to disable demo accounts after training. Module exceptions are under **Administration → Module Access**. The six accounts have different generated passwords; this sheet must stay private. Change or reset a demo password through the normal account controls when needed.

The explicit server-only command `team_server.py create-demo` creates this demonstration once and takes a consistent database backup first. Repeating it refuses to overwrite the existing credential sheet or reset the campaign/accounts. It is not a remote or unauthenticated API. The private credential file and database backups are in Data and must not be included in employee/client distributions.
