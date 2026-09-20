"""
mail.py - the one place this API sends email.

SMALL ON PURPOSE. It exists so that the next thing the API has to send does
not grow a second SES client, a second sender and a second opinion about what
a failure means. Composing the message belongs to whoever is sending it; this
holds the sender, the client, and the rule about failure.

A SEND NEVER RAISES INTO THE CALLER. Every message this API sends is the
second half of something already done - a seat reserved, a token minted - and
that first half is written and committed before the send is attempted.
Letting SES take the request down with it would mean a seat reserved, a token
shown to nobody, and a 500 on the screen of the person who invited somebody
successfully. So `send` returns True or False and logs the reason, and the
caller reports which it was.

SENDER IS READ LAZILY, not at import. app.py reads its required variables at
import and a missing one is a KeyError before any route runs - which is right
for a bucket name every route needs, and wrong for this: a missing SENDER
would take down fifty routes that send nothing. It fails at the send, where
it is about to matter, and says so.
"""

import os

import boto3

_ses = boto3.client("ses")


def sender():
    """The verified address every message goes out as. Terraform's, from the
    same variable the signup function uses - one sender, one verified
    identity, one thing to change."""
    return os.environ.get("SENDER") or ""


def send(to, subject, body, reply_to=None):
    """One plain-text message. True where SES accepted it.

    Plain text rather than HTML: every message this product sends is a
    sentence, a link and a date. HTML would add a template to maintain, a
    second copy of every word, and a class of rendering problem in other
    people's mail clients that we could not see.
    """
    address = sender()
    if not address:
        print("[mail-not-sent] to=%s reason=no-sender" % _mask(to))
        return False

    try:
        _ses.send_email(
            Source=address,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
            # The administrator who invited them, so a reply reaches a person
            # rather than a mailbox that does not exist - arqedia.com
            # publishes no MX record and a reply to the sender goes nowhere.
            **({"ReplyToAddresses": [reply_to]} if reply_to else {}),
        )
        print("[mail-sent] to=%s subject=%r" % (_mask(to), subject))
        return True
    except Exception as exc:  # noqa: BLE001 - the caller's work already stands
        print("[mail-failed] to=%s subject=%r %r" % (_mask(to), subject, exc))
        return False


def _mask(address):
    """An address in a log, without being an address in a log. The domain is
    what makes a delivery failure diagnosable; the local part is the personal
    data and is not what anybody is grepping for."""
    if not address or "@" not in address:
        return "?"
    local, domain = address.split("@", 1)
    return (local[:1] or "?") + "***@" + domain


# --- what the invitation says ----------------------------------------------

def invitation(invited_by, accept_url, expires_at, role):
    """The seat invitation, as one plain message.

    IT NAMES WHO SENT IT. An unexpected link to a product nobody has heard of
    is a phishing email; the same link from a colleague at the same firm is an
    invitation. The name of the person who invited them is the only thing that
    makes the difference, so it is in the subject as well as the body.

    IT DOES NOT SAY WHAT THE WORKSPACE HOLDS. Nothing about this tenant is
    visible to somebody who has not accepted, and that includes its name in an
    email to an address that may not be theirs yet.
    """
    subject = "%s has invited you to ARQEDIA" % invited_by
    body = (
        "%s has given you a seat in their ARQEDIA workspace, as %s.\n"
        "\n"
        "Open this link to accept it and set a password:\n"
        "\n"
        "%s\n"
        "\n"
        "The invitation lapses on %s, and the seat it reserves goes back to "
        "the workspace.\n"
        "\n"
        "If you were not expecting this, you can ignore it - nothing has been "
        "created in your name and nothing will be.\n"
        "\n"
        "ARQEDIA\n"
        "This address does not take replies; use Reply and it will reach %s.\n"
    ) % (invited_by,
         "an administrator" if role == "admin" else "a member",
         accept_url,
         str(expires_at)[:10],
         invited_by)
    return subject, body
