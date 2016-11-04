## Script (Python) "shortcut_add"
##title=Add item to favourites
##parameters=shortcut_id, shortcut_title, description, remote_uid
# $Id: shortcut_add.py,v 1.1 2003/06/06 14:44:25 ikuleshov Exp $
# $Revision: 1.1 $
from Products.ExpressSuiteTools.SecureImports import cookId

shortcut_id = cookId(context, shortcut_id)
context.manage_addProduct['ExpressSuiteTools'].addShortcut( id=shortcut_id
                                                    , title=shortcut_title
                                                    , description=description
                                                    , remote=remote_uid
                                                    )

return context.REQUEST['RESPONSE'].redirect(context.absolute_url(), status=303)
