"""Compact, visible department actions above the existing lead grid."""
from collections import Counter
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton


class HandoffControls:
    def build_handoff_controls(self):
        self.handoff_bar=QWidget(); root=QVBoxLayout(self.handoff_bar); root.setContentsMargins(0,0,0,0); root.setSpacing(3)
        row=QHBoxLayout(); row.setSpacing(6); root.addLayout(row)
        self.handoff_title=QLabel('Operations → Quality → Delivery'); self.handoff_title.setObjectName('sectionTitle'); row.addWidget(self.handoff_title)
        row.addStretch(1)
        self.incoming_button=QPushButton('Incoming leads'); self.incoming_button.setToolTip('Show unassigned incoming records in this same workspace.'); self.incoming_button.clicked.connect(lambda:self.set_workspace_mode('incoming')); row.addWidget(self.incoming_button)
        self.stage_button=QPushButton('Review / change stage'); self.stage_button.clicked.connect(self.workflow_action); row.addWidget(self.stage_button)
        self.assign_button=QPushButton('Assign selected'); self.assign_button.clicked.connect(self.assign_leads); row.addWidget(self.assign_button)
        self.push_button=QPushButton('Push to Department'); self.push_button.setObjectName('primaryButton'); self.push_button.clicked.connect(self.transfer_leads); row.addWidget(self.push_button)
        self.handoff_hint=QLabel(); self.handoff_hint.setObjectName('muted'); self.handoff_hint.setTextFormat(Qt.TextFormat.PlainText); self.handoff_hint.setWordWrap(True); root.addWidget(self.handoff_hint)

    def update_handoff_controls(self,*_):
        if not hasattr(self,'push_button'):return
        user=self.client.user or {}; supervisor=user.get('role') in ('Super User','Department Manager','Team Lead')
        draft=self.scope.currentData() in ('draft','all_sheets')
        rows=[self.controller.lead_rows[i] for i in self.leads.selected_rows() if i<len(self.controller.lead_rows)] if not draft and self.controller.mode=='records' else []
        department=user.get('department_id')
        departments={r['department_id'] for r in rows}
        own_department=user.get('role')=='Super User' or all(r['department_id']==department for r in rows)
        if user.get('role')=='Super User' and len(departments)==1:department=next(iter(departments))
        destination={'operations':'Quality','quality':'Delivery'}.get(department)
        self.push_button.setText('Push to '+destination if destination else 'Push to Department')
        self.incoming_button.setVisible(supervisor)
        for button in (self.stage_button,self.assign_button,self.push_button):
            button.setVisible(not draft and (button is self.stage_button or supervisor))
            button.setEnabled(bool(rows) and own_department and not self.busy)
        self.push_button.setToolTip('Select rows, then preview eligibility and confirm the handoff. Only the selected leads are sent.')
        self.assign_button.setToolTip('Choose who in your department should work on the selected leads.')
        count=len(rows)
        states=', '.join(f'{n} {state}' for state,n in Counter(r['state'] for r in rows).items())
        prefix=f'{count} selected · {states}. ' if count else 'Select rows by clicking their row numbers; Ctrl-click adds more rows. '
        guidance={
            'operations':'Review / change stage → Submit for review → Approve selected → Push to Quality.',
            'quality':'Incoming leads → Assign selected; review and mark Quality Qualified → Push to Delivery.',
            'delivery':'Incoming leads → Assign selected; approve delivery, then mark Delivered.',
        }.get(department,'Review / change stage prepares selected leads; Push to Department previews their handoff.')
        if len({r['state'] for r in rows})==1:
            guidance={
                'Validated':'Use Review / change stage → Submit for review.',
                'Pending Team Lead Review':'Use Review / change stage → Approve selected, then Push to Quality.' if supervisor else 'Waiting for your Team Lead to approve these leads.',
                'Approved':'Ready for the handoff preview. Click Push to Quality.' if department=='operations' else guidance,
                'Transferred to Quality':'Assign selected to a reviewer, then Review / change stage → Start quality review.',
                'Quality In Progress':'Review the details, then Review / change stage → Mark quality qualified (or choose another quality outcome).',
                'Quality Qualified':'Ready for the handoff preview. Click Push to Delivery.' if department=='quality' else guidance,
                'Transferred to Delivery':'Assign selected, then Review / change stage → Approve delivery.',
                'Delivery Approved':'Use Review / change stage → Mark delivered after delivery is completed.',
                'Delivered':'Delivery is complete. Use View History to inspect the full handoff trail.',
            }.get(rows[0]['state'],guidance)
        if draft:
            if self.controller.read_only_sheet:
                prefix='Read-only inspection. '
                guidance='Use Sheets → Duplicate sheet to create your own editable copy.'
            else:
                prefix='Private draft: validate and commit before sending leads. '
                guidance=('Choose Records: All leads to review committed rows.' if user.get('role')=='Super User' else 'Choose Records: All permitted leads to review committed rows.') if supervisor else 'Choose Records: Assigned / owned by me to submit committed rows for review.'
        elif rows and not own_department:
            guidance='Transferred leads are handled by the receiving department. Use View History to follow their progress.'
        self.handoff_hint.setText(prefix+guidance)
        self.handoff_hint.setToolTip(prefix+guidance)
        if hasattr(self,'excel_workspace'):self.excel_workspace.update_mode()
