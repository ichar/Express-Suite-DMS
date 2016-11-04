## Script (Python) "object_by_uid"
##parameters=uid, base=None
##title=
# $Id: object_by_uid.py,v 1.2 2003/07/28 11:31:42 Exp $
# $Revision: 1.2 $
from Products.ExpressSuiteTools.SecureImports import getObjectByUid
ob = getObjectByUid( context, uid )
if ob is None:
    return None
return base and ob.getBase() or ob
