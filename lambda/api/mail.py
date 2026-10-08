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
import re

import boto3

_ses = boto3.client("ses")


def sender():
    """The verified address every message goes out as. Terraform's, from the
    same variable the signup function uses - one sender, one verified
    identity, one thing to change."""
    return os.environ.get("SENDER") or ""


# A well-formed address, the shape SES itself insists on. Anything else in a
# message's recipients makes SES reject the WHOLE message (SES developer
# guide, "How email sending works") - so a BCC is only ever added in this
# shape, and the API's own fallback for a token with no email, "unknown",
# never reaches SES as a recipient.
_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def send(to, subject, body, reply_to=None, bcc=None):
    """One plain-text message. True where SES accepted it for `to`.

    Plain text rather than HTML: every message this product sends is a
    sentence, a link and a date. HTML would add a template to maintain, a
    second copy of every word, and a class of rendering problem in other
    people's mail clients that we could not see.

    A BCC NEVER COSTS THE RECIPIENT THEIR EMAIL (feature/share-sender-copy).
    It is added only when well formed and not the recipient's own address,
    and a send that SES refuses with it is sent again without it - the only
    case in which this makes a second call. True means `to` was sent to; the
    copy is a courtesy, logged either way.
    """
    address = sender()
    if not address:
        print("[mail-not-sent] to=%s reason=no-sender" % _mask(to))
        return False

    copy = (bcc or "").strip()
    if copy and (not _ADDRESS.match(copy)
                 or copy.lower() == str(to or "").strip().lower()):
        print("[mail-bcc-skipped] to=%s bcc=%s" % (_mask(to), _mask(copy)))
        copy = ""

    def attempt(with_copy):
        destination = {"ToAddresses": [to]}
        if with_copy:
            destination["BccAddresses"] = [with_copy]
        _ses.send_email(
            Source=address,
            Destination=destination,
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
            # The administrator who invited them, so a reply reaches a person
            # rather than a mailbox that does not exist - arqedia.com
            # publishes no MX record and a reply to the sender goes nowhere.
            **({"ReplyToAddresses": [reply_to]} if reply_to else {}),
        )

    try:
        attempt(copy)
        print("[mail-sent] to=%s subject=%r bcc=%s" % (
            _mask(to), subject, _mask(copy) if copy else "-"))
        return True
    except Exception as exc:  # noqa: BLE001 - the caller's work already stands
        if not copy:
            print("[mail-failed] to=%s subject=%r %r" % (_mask(to), subject,
                                                          exc))
            return False
        print("[mail-bcc-refused] to=%s bcc=%s %r - sending without it" % (
            _mask(to), _mask(copy), exc))

    try:
        attempt("")
        print("[mail-sent] to=%s subject=%r bcc=dropped" % (_mask(to),
                                                            subject))
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


# --- what a share says -----------------------------------------------------

def share_invitation(shared_by, tenant_name, memo_label, subject, link,
                     expires_at, expiry_set_by_tenant):
    """A memorandum, shared with somebody outside the workspace.

    IT NAMES THE PERSON AND THE FIRM. Unlike a seat invitation, the recipient
    is the intended reader of what was sent, and an unexpected link from a
    product nobody has heard of is a phishing email; the same link from a
    named person at a named firm is a document they were expecting. The
    sender's address is the Reply-To.

    IT SAYS WHAT THE MEMORANDUM IS ABOUT, and nothing else from it. A
    recipient who has only clicked the link has no relationship with us
    (share_viewer_spec section 7): this is transactional email about one
    memorandum, and carries no marketing.

    IT SAYS WHAT REGISTERING DOES only where registering would do it. A date
    the tenant chose is a ceiling, and promising six months over it would be
    untrue.
    """
    mail_subject = "%s has shared a memorandum with you" % shared_by
    keep = ("" if expiry_set_by_tenant else
            "Your access lasts two weeks. If you register - a password and an "
            "authenticator app - it lasts six months from when this was "
            "shared.\n\n")
    body = (
        "%s at %s has shared a memorandum with you through ARQEDIA:\n"
        "\n"
        "    %s\n"
        "    %s\n"
        "\n"
        "Open it here:\n"
        "\n"
        "%s\n"
        "\n"
        # The link alone opens nothing on a browser it has not been used on
        # (fix/share-link-possession-read). Said here, so the code email that
        # follows the first open is expected rather than alarming.
        "The first time you open it on a device, we'll email you a code to "
        "confirm it's you.\n"
        "\n"
        "The link is yours: it identifies you, and every page you read or "
        "download carries your address. Please do not forward it.\n"
        "\n"
        "Access ends on %s.\n"
        "\n"
        "%s"
        "If you were not expecting this, you can ignore it.\n"
        "\n"
        "ARQEDIA\n"
        "This address does not take replies; use Reply and it will reach %s.\n"
    ) % (shared_by, tenant_name, memo_label, subject or "", link,
         str(expires_at)[:10], keep, shared_by)
    return mail_subject, body
