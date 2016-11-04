"""
Secure symbols available for import from Python Scripts
$Id: SecureImports.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 13/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
from Exceptions import formatErrorValue, SimpleError, ResourceLockedError, InvalidIdError, ReservedIdError, \
     DuplicateIdError, CopyError, Unauthorized

from DateTime import DateTime

from Globals import PersistentMapping
from persistent.list import PersistentList

from Config import Roles
from DepartmentDictionary import departmentDictionary
from Mail import MailMessage
from SimpleObjects import SimpleRecord
from PortalLogger import portal_log, portal_info, portal_error, print_traceback
from TransactionManager import BeginThread, CommitThread, UpdateRequestRuntime

from Utils import refreshClientFrame, addQueryString, getObjectByUid, CreateObjectCopy, TypeOFSAction, \
     parseTitle, parseString, parseDate, parseDateValue, parseTime, parseDateTime, parseMemberIDList, \
     cookId, translit_string, check_unique_subject, joinpath, makeTuple, \
     GetSessionValue, SetSessionValue, ExpireSessionValue

from TemporalExpressions import DailyTE, WeeklyTE, MonthlyByDayTE, \
     MonthlyByDateTE, YearlyTE, DateTimeTE, \
     UnionTE, UniformIntervalTE

from CustomObjects import ObjectHasCustomCategory, SendToUsers, CustomDefs, SetCustomBaseRoles, \
     CustomReplyToAction

# end of imported symbols

from AccessControl import ModuleSecurityInfo, allow_class
from types import ClassType

# make everything in this module public
ModuleSecurityInfo(__name__).setDefaultAccess(1)

name = item = value = None

for name, item in globals().items():
    # skip hidden (protected attributes)
    if name.startswith('_'):
        continue

    # __basicnew__ is used to check for extension classes
    if type(item) is ClassType or hasattr( item, '__basicnew__' ):
        # skip classes with existing permissions
        if item.__dict__.has_key( '__ac_permissions__' ):
            continue

        # skip classes with existing ClassSecurityInfo
        for value in item.__dict__.values():
            if hasattr( value, '__security_info__' ):
                break
        else:
            # the class has no security info on it, make it public
            allow_class( item )
            # allow setitem and getitem calls too
            # XXX what about setattr and delattr???
            if hasattr( item, '__setitem__' ) and not hasattr( item, '__guarded_setitem__' ):
                item.__guarded_setitem__ = item.__setitem__
            if hasattr( item, '__delitem__' ) and not hasattr( item, '__guarded_delitem__' ):
                item.__guarded_delitem__ = item.__delitem__

del name, item, value
del ModuleSecurityInfo, allow_class, ClassType
