## Script (Python) "registry_edit"
##parameters=REQUEST, record_id, comment=''
##title=Edit entry
# $Id: registry_edit.py,v 1.1 2003/07/01 10:39:50 ikuleshov Exp $
# $Revision: 1.1 $
message = ""
r = REQUEST.get

context.editEntry(record_id, REQUEST=REQUEST, comment=comment, redirect=0)

message = "Entry changed"
REQUEST[ 'RESPONSE' ].redirect( context.absolute_url() 
                              + '?portal_status_message=' + message)
