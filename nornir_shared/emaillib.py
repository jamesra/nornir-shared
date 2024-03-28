'''



'''

import os
import typing
import smtplib
from email import encoders
from email.mime import multipart, text, image

from . import prettyoutput


class EmailArgs(typing.NamedTuple):
    host: str
    username: str
    password: str
    subject: str
    toAddresses: typing.List[str] | str
    ccAddresses: typing.List[str] | str | None
    fromAddress: str
    fromFriendlyAddress: str
    message: str
    files: typing.List[str]
    port: int = 25

def SendMail(args: EmailArgs):
    """Sends an email"""

    if not args.toAddresses and not args.ccAddresses:
        prettyoutput.Log('No Email addresses specified for report, no report E-mailed.')
        return

    if isinstance(args.toAddresses, list):
        to_address_string = ', '.join(args.toAddresses)
    else:
        assert (isinstance(args.toAddresses, str))
        to_address_string = args.toAddresses
        to_address_list = [args.toAddresses]

    if isinstance(args.ccAddresses, list):
        cc_address_string = ', '.join(args.ccAddresses)
    elif args.ccAddresses is not None:
        assert (isinstance(args.ccAddresses, str))
        cc_address_string = args.ccAddresses
        cc_address_list = [args.ccAddresses]

    smtpConn = smtplib.SMTP(args.host, args.port)
    try:
        smtpConn.set_debuglevel(False)
        try:
            smtpConn.starttls()
        except:
            prettyoutput.Log("Could not start secure session")

        try:
            if args.username is not None:
                smtpConn.login(args.username, args.password)
        except:
            prettyoutput.Log("Could not use provided credentials")

        #        #Build the message
        #        ConcatenatedToAddress = ""
        #        if not toAddresses is None:
        #            ConcatenatedToAddress = ','.join(toAddresses)
        #
        #        ConcatenatedCCAddress = ','.join(ccAddresses)

        msg = multipart.MIMEMultipart()
        msg['Subject'] = args.subject
        msg['From'] = f'{args.fromFriendlyAddress} [{args.fromAddress}]'
        msg['reply-to'] = args.fromAddress
        msg['To'] = to_address_string
        msg['cc'] = cc_address_string
        msg.attach(text.MIMEText(args.message))

        if not args.files is None:
            for f in args.files:
                if not os.path.exists(f):
                    prettyoutput.Log("Attachment Not found: " + f)
                    continue

                with open(f, 'rb') as hFile:
                    Data = hFile.read()
                    part = image.MIMEImage(Data)
                    part.set_payload(Data)
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', 'attachment filename="%s"' % f)
                    msg.attach(part)

        prettyoutput.Log("\nTo: " + to_address_string)
        prettyoutput.Log("\nCC: " + cc_address_string)
        prettyoutput.Log("Message:")
        prettyoutput.Log('\t' + args.message)

        AllRecipientAddresses = args.to_address_list + args.cc_address_list

        smtpConn.sendmail(args.fromAddress,
                          AllRecipientAddresses,
                          msg.as_string())
    finally:
        smtpConn.quit()


if __name__ == '__main__':
    # Email the completion notice

    args = EmailArgs(host='smtp.utah.edu',
                     username=None,
                     password=None,
                     subject="Build progress",
                     toAddresses=["u0490822@utah.edu"],
                     ccAddresses="",
                     fromAddress="james.r.anderson@utah.edu",
                     message="A build has completed.",
                     port=25,
                     fromFriendlyAddress="Build Notifications")

    SendMail(args)
    pass
