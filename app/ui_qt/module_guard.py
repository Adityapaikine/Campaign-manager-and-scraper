"""Recheck local-tool permissions without blocking the Qt event loop."""
from functools import wraps


def authorized(module):
    def decorate(method):
        @wraps(method)
        def invoke(self, *args, **kwargs):
            check = getattr(self.controller, 'request_module_action', None)
            if check is None:
                return method(self, *args, **kwargs)
            denied=getattr(self,'module_action_denied',None)
            return check(module, lambda: method(self, *args, **kwargs),
                         on_denied=(lambda:denied(method.__name__,args)) if denied else None)
        return invoke
    return decorate
