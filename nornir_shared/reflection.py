'''
Created on Jul 11, 2012

@author: Jamesan
'''

from . import  prettyoutput


__ModuleClassCacheDict = dict();

def get_module_class(module, kls, LogErrIfNotFound=True):
    '''Load a class from a string'''

    key = module + '.' + kls;

    if key in __ModuleClassCacheDict:
        m = __ModuleClassCacheDict[key];
        return m;

    # m = importlib.import_module(module);
    m = __import__(module, fromlist=['*'])
    parts = kls.split('.')

    try:
        for comp in parts:
            m = getattr(m, comp)
    except AttributeError as E:
        m = None;
        if(LogErrIfNotFound):
            prettyoutput.LogErr(str(E) + " " + module + " , " + kls);
        pass

    __ModuleClassCacheDict[key] = m;

    return m

def get_class(kls):
    '''Load a class from a string'''

    if kls in __ModuleClassCacheDict:
        m = __ModuleClassCacheDict[kls];
        return m;

    parts = kls.split('.')
    if(len(parts) > 0):
        module = ".".join(parts[:-1])
        m = __import__(module)
        for comp in parts[1:]:
            m = getattr(m, comp)
            __ModuleClassCacheDict[kls] = m;
            return m
    else:
        getattr()

if __name__ == '__main__':
    pass
