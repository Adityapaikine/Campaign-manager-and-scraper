"""Module access is independent of record scope, field policies and workflow roles."""
from app.team.access import require, audit

MODULES = {
    'dashboard': 'Dashboard', 'leads': 'Lead Workspace', 'scraper': 'Scraper',
    'campaigns': 'Campaign Manager', 'validation': 'Validation Summary',
    'ai': 'AI Center', 'reports': 'Reports', 'tools': 'Activity & Diagnostics',
    'settings': 'Settings', 'administration': 'Administration',
}

# Every public operation has an explicit gate. Context and session endpoints do
# not reveal lead records and remain available when navigation is restricted.
OPERATION_MODULES = {
    **dict.fromkeys(('me','logout','change_password','directory','campaigns','preferences',
                     'modules','module_check'), ()),
    **dict.fromkeys(('module_policy','module_policy_save','user_save','department_save',
                     'policy','policy_save'), ('administration',)),
    **dict.fromkeys(('campaign_save','campaign_assign','campaign_package','campaign_rules',
                     'legacy_snapshots'), ('campaigns',)),
    **dict.fromkeys(('field_access','bulk_edit','export_draft','commit','leads','lead','lead_edit',
                     'archive','history','export','sheet_recovery','sheets','sheet_create','sheet_load',
                     'sheet_save','sheet_rename','sheet_delete','assignment_options','assign',
                     'workflow_options','selection_actions','transition','transfer','rework','transfer_history','comments',
                     'historical_assignment','populate'), ('leads',)),
    **dict.fromkeys(('validate_draft','validate_leads','commit'), ('leads','validation')),
    'notifications': (), 'dashboard': ('dashboard',), 'report': ('reports',),
    'report_export': ('reports',), 'audit': ('tools',),
}


def module_access(db, user):
    overrides = {(r['subject_type'], r['subject_id'], r['module']): bool(r['allowed'])
                 for r in db.execute('SELECT * FROM team_module_permissions WHERE '
                                     "(subject_type='user' AND subject_id=?) OR "
                                     "(subject_type='department' AND subject_id=?)",
                                     (user['id'], user['department_id']))}
    result = {}
    for module, label in MODULES.items():
        if user['role'] == 'Super User':
            allowed, source = True, 'Super User'
        elif module == 'administration':
            allowed, source = False, 'Super User only'
        elif ('user', user['id'], module) in overrides:
            allowed, source = overrides['user', user['id'], module], 'User override'
        elif ('department', user['department_id'], module) in overrides:
            allowed, source = overrides['department', user['department_id'], module], 'Department'
        else:
            allowed = module != 'tools' and not (module == 'scraper' and user['department_id'] in ('quality','delivery'))
            source = 'Default'
        result[module] = {'label': label, 'allowed': allowed, 'source': source}
    return result


def require_module(db, user, module):
    require(module in MODULES, 'Unknown module.', 400)
    require(module_access(db, user)[module]['allowed'],
            f'Your account does not have access to {MODULES[module]}. Contact your Super User.', 403)


class ModulePermissions:
    def op_modules(self, db, user):
        return module_access(db, user)

    def op_module_check(self, db, user, module):
        # Local tools recheck this before starting work; server operations are
        # independently checked in Service.call, never trusting a client flag.
        require_module(db, user, module)
        return {'allowed': True}

    def op_module_policy(self, db, user, subject_type, subject_id):
        require(user['role'] == 'Super User')
        subject = self._module_subject(db, subject_type, subject_id)
        overrides = {r['module']: bool(r['allowed']) for r in db.execute(
            'SELECT module,allowed FROM team_module_permissions WHERE subject_type=? AND subject_id=?',
            (subject_type, subject_id))}
        effective = module_access(db, subject) if subject_type == 'user' else {}
        return {'overrides': overrides, 'effective': effective, 'modules': MODULES}

    def _module_subject(self, db, subject_type, subject_id):
        require(subject_type in ('department','user'), 'Choose a department or user.', 400)
        table = 'team_departments' if subject_type == 'department' else 'team_users'
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (subject_id,)).fetchone()
        require(row is not None, 'Department or user unavailable.', 404)
        return row

    def op_module_policy_save(self, db, user, subject_type, subject_id, overrides):
        require(user['role'] == 'Super User')
        self._module_subject(db, subject_type, subject_id)
        require(isinstance(overrides, dict) and set(overrides) <= set(MODULES), 'Unknown module.', 400)
        require(all(v is None or type(v) is bool for v in overrides.values()), 'Use Allow, Deny or Inherit.', 400)
        for module, allowed in overrides.items():
            require(module != 'administration', 'Administration remains Super User only.', 400)
            if allowed is None:
                db.execute('DELETE FROM team_module_permissions WHERE subject_type=? AND subject_id=? AND module=?',
                           (subject_type, subject_id, module))
            else:
                db.execute('INSERT INTO team_module_permissions(subject_type,subject_id,module,allowed) VALUES(?,?,?,?) '
                           'ON CONFLICT(subject_type,subject_id,module) DO UPDATE SET allowed=excluded.allowed',
                           (subject_type, subject_id, module, int(allowed)))
        audit(db, user, 'module-access-save', subject_id, details={'subject_type': subject_type, 'overrides': overrides})
        return self.op_module_policy(db, user, subject_type, subject_id)
