
import smtplib
import nornir_shared.prettyoutput as PrettyOutput
import os
from email.mime import multipart, text, image
from email.utils import COMMASPACE, formatdate
from email import encoders

def SendMail(**kwargs):
    host = kwargs.get('host', 'smtp.utah.edu');
    username = kwargs.get('username', 'u0490822');
    password = kwargs.get('password', '4IsTheNumber');
    subject = kwargs.get('subject', "Build progress");
    toAddresses = kwargs.get('to', "u0388504@utah.edu");
    ccAddresses = kwargs.get('cc' , "");
    fromAddress = kwargs.get('from', "james.r.anderson@utah.edu");
    fromFriendlyAddress = kwargs.get('fromFriendlyAddress' , "Build Script Pipeline");
    message = kwargs.get('message', "A build has completed.");
    files = (str(kwargs.get('files', []))).split(',');
    port = kwargs.get('port', 25);

    toAddressList = toAddresses;
    ccAddressList = ccAddresses;

    if isinstance(toAddresses, list):
        toAddressString = ', '.join(toAddresses);
    else:
        assert(isinstance(toAddresses, str));
        toAddressString = toAddresses;
        toAddressList = [toAddressList];

    if isinstance(ccAddresses, list):
        ccAddressString = ', '.join(ccAddresses);
    else:
        assert(isinstance(ccAddresses, str));
        ccAddressString = ccAddresses;
        ccAddressList = [ccAddressList];

    if len(toAddressString) == 0 and len(ccAddressString) == 0:
        PrettyOutput.Log('No Email addresses specified for report, no report E-mailed.')
        return;



    smtpConn = smtplib.SMTP(host, port);
    try:
        smtpConn.set_debuglevel(False);
        try:
        	smtpConn.starttls();
        except:
        	PrettyOutput.Log("Could not start secure session");

        try:
        	if(username is not None):
        		smtpConn.login(username, password);
        except:
        	PrettyOutput.Log("Could not use provided credentials");

#        #Build the message
#        ConcatenatedToAddress = "";
#        if not toAddresses is None:
#            ConcatenatedToAddress = ','.join(toAddresses);
#
#        ConcatenatedCCAddress = ','.join(ccAddresses);

        msg = multipart.MIMEMultipart();
        msg['Subject'] = subject;
        msg['From'] = fromFriendlyAddress + ' [' + fromAddress + ']';
        msg['reply-to'] = fromAddress;
        msg['To'] = toAddressString;
        msg['cc'] = ccAddressString;
        msg.attach(text.MIMEText(message));

        if not files is None:
            for f in files:
                if not os.path.exists(f):
                    PrettyOutput.Log("Attachment Not found: " + f);
                    continue;

                hFile = open(f, 'rb');
                Data = hFile.read();
                hFile.close();
                hFile = None;

                part = image.MIMEImage(Data)
                part.set_payload(Data);
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment; filename="%s"' % f);
                msg.attach(part);


        PrettyOutput.Log("\nTo: " + toAddressString);
        PrettyOutput.Log("\nCC: " + ccAddressString);
        PrettyOutput.Log("Message:");
        PrettyOutput.Log('\t' + message);

        AllRecipientAddresses = toAddressList + ccAddressList;

        smtpConn.sendmail(fromAddress,
						   AllRecipientAddresses,
						   msg.as_string());
    finally:
        smtpConn.quit();


if __name__ == '__main__':
    # Email the completion notice
    class EmailArgs(object): pass

    Email = EmailArgs();
    Email.subject = "Build progress";
    Email.toAddresses = ["u0388504@utah.edu"]
    Email.ccAddresses = ""
    Email.fromAddress = "james.r.anderson@utah.edu";
    Email.fromFriendlyAddress = "Build Notifications";
    Email.message = "A build has completed.";
    Email.host = 'smtp.utah.edu';
    Email.port = 25;

    SendMail(Email);
    pass
