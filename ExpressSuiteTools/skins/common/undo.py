## Script (Python) "undo"
##title=Undo transactions
##parameters=transaction_info
context.portal_undo.undo(context, transaction_info)

return context.REQUEST.RESPONSE.redirect(
    context.portal_url()+'/undo_form?portal_status_message=Transaction(s)+undone' )
