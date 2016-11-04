## Script (Python) "export_to_excel"
##title=Export data to Excel

REQUEST = context.REQUEST
setHeader = REQUEST.RESPONSE.setHeader
tasks = REQUEST.get('tasks', [])

lang = context.portal_membership.getLanguage (REQUEST=REQUEST)
filename = context.msg('Report')

#export_excel_form = Globals.DTMLFile ('export_excel_form', context.globals())
#excel_form = context.excel_form

setHeader = REQUEST.RESPONSE.setHeader
setHeader("Content-Type", "application/vnd.ms-excel; name='excel'");
setHeader("Content-type", "application/octet-stream");
setHeader("Content-Disposition", "attachment; filename=%s.xls" % filename);
setHeader("Cache-Control", "must-revalidate, post-check=0, pre-check=0");
setHeader("Pragma", "no-cache");
setHeader("Expires", "0");

return context.excel_form(context, tasks=tasks, REQUEST=REQUEST)