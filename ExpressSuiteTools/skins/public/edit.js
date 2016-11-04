function clearLinkField( uid, title ) {
    try {
      document.forms[0][uid].value = '';
      document.forms[0][title].value = '';
    }
    catch (error) { 
      //alert("clearLinkField error (entry_field_edit): " + uid + title); 
	  return;
    }
}

function callbackLinkTemplate( formId, uid, title, version_id, uid_field, title_field ) {
    try {
      document.forms[formId][uid_field].value = uid;
      document.forms[formId][title_field].value = title;
    }
    catch (error) { 
	  //alert("callbackFunction error (entry_field_edit): " + formId + "-" + uid_field + "-" + title_field); 
	  return; 
    }
}

function callbackTextTemplate( formId, value_field, value ) {
    try {
      document.forms[formId][value_field].value = value;
    }
    catch (error) { 
	  return; 
    }
}

function setFolderUrl( uid, title, uid_field, title_field ) {
    try {
      document.forms[0][uid_field].value = uid;
      document.forms[0][title_field].value = title;
    }
    catch (error) { 
	  return; 
    }
}

