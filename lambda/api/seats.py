"""
seats.py - who belongs to a tenant, and what they may do.

Self-contained, for the same reason wallet.py is: app.py imports this, and
two modules that import each other are a circular import waiting to be
discovered at deploy time.

Two rules shape it.

A SEAT IS TAKEN ON ACCEPTANCE. An invitation reserves one for seven days and
then lapses. Otherwise an administrator invites three people, two never reply,
and a firm that paid for five seats can use three - with nothing on any screen
explaining why.

THE LAST ADMINISTRATOR CANNOT BE REMOVED OR DEMOTED. Not as a courtesy: a
tenant with no administrator cannot change its own plan, its card, its brand
or its seats, and the only route back is a support request that takes days.
The check is here rather than in the front end, because the front end can be
bypassed by anyone calling the API.

A MEMBER SEES THE WORKSPACES ASSIGNED TO THEIR SEAT; AN ADMINISTRATOR SEES
EVERY ONE (PACK-02 C, migration 045, decided 23 October 2026). Assignment is
seat_workspace. An invitation names its workspaces - at least one for a
member - in seat_invitation_workspace, and the signup function copies them to
the seat on acceptance. A new workspace is assigned to no member. An
administrator made a member keeps every workspace there is, so nothing they
could see disappears.
"""

import hashlib
import os
import secrets
import time
import datetime

import boto3
from botocore.exceptions import ClientError

_rds = boto3.client("rds-data")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

# Long enough to survive a holiday, short enough that nobody has to chase.
INVITE_DAYS = 7

ROLES = ("admin", "member")


class SeatsFull(Exception):
    """Every seat the plan buys is taken or reserved."""


class LastAdmin(Exception):
    """The only administrator. Removing or demoting them locks the tenant out
    of its own plan, card, brand and seats."""


# --- plumbing --------------------------------------------------------------

def _sql(statement, params=None):
    for _ in range(12):
        try:
            return _rds.execute_statement(
                resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                database=DATABASE, sql=statement, parameters=params or [])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in (
                "DatabaseResumingException", "ThrottlingException"
            ):
                time.sleep(3)
                continue
            raise
    raise RuntimeError("cluster did not resume")


def _p(name, value):
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _col(record, i):
    cell = record[i]
    for kind in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if kind in cell:
            return cell[kind]
    return None


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- how many a plan buys --------------------------------------------------
#
# PLAN_SEATS AND DEFAULT_SEATS ARE GONE (18.5). They were a second copy of
# plan.seat_count in Python:
#
#     PLAN_SEATS = {"base": 2, "business": 5, "small_business": 5}
#     DEFAULT_SEATS = 2
#
# Worse than a duplicate, because it had a key the table does not - there has
# never been a plan row called small_business, and tenant.plan has never held
# that string either:
#
#     SELECT plan, COUNT(*) FROM tenant GROUP BY plan
#     -> base | 2
#     -> business | 3
#
# So the alias covered a value nothing has ever written, and the two numbers
# agreed with the table only because nobody had changed a plan yet. CLAUDE.md
# has had this open as "Seat counts as data" since the wallet was built; this
# closes it.


def seats_bought(tenant_id):
    """How many seats this tenant has, read from the plan table and nowhere
    else.

    subscription.plan_id IS THE PLAN (CLAUDE.md, Money). Its seat_count
    decides, and that is the first query.

    tenant.plan is the fallback and is only reached on a trial, where there is
    no subscription row. It is a plan_key, so it is now resolved THROUGH the
    table rather than through a map beside it - which is the whole of this
    change. The folding is kept exactly as it was ("Small Business" ->
    small_business) so that a value written by an older path still resolves as
    far as it ever did.

    AN UNKNOWN PLAN GETS THE SMALLEST ACTIVE ONE, which is what DEFAULT_SEATS
    was for and is now read rather than written down. A tenant whose plan
    string we do not recognise should be inconvenienced, not locked out of its
    own workspace - and hard-coding the number was how that intention became a
    third place seats were recorded.

    Zero only where the plan table holds no active row at all, which migration
    018 seeds and nothing deletes. It is not a lock-out: existing seats keep
    working, and what it refuses is inviting somebody new."""
    rows = _sql(
        "SELECT p.seat_count FROM subscription s "
        "JOIN plan p ON p.plan_id = s.plan_id WHERE s.tenant_id = :t",
        [_p("t", tenant_id)]).get("records", [])
    if rows:
        return int(_col(rows[0], 0))

    rows = _sql("SELECT plan FROM tenant WHERE tenant_id = :t",
                [_p("t", tenant_id)]).get("records", [])
    plan = (_col(rows[0], 0) if rows else "base") or "base"
    key = plan.strip().lower().replace(" ", "_")

    rows = _sql(
        "SELECT seat_count FROM plan WHERE plan_key = :k AND active = 1",
        [_p("k", key)]).get("records", [])
    if rows:
        return int(_col(rows[0], 0))

    rows = _sql(
        "SELECT seat_count FROM plan WHERE active = 1 "
        "ORDER BY monthly_price_cents LIMIT 1").get("records", [])
    return int(_col(rows[0], 0)) if rows else 0


# --- reading ---------------------------------------------------------------

def _home_domain(tenant_id):
    """The domain this tenant signed up on.

    tenant_domain is where the one-trial-per-domain rule lives, so it is
    already the record of whose workspace this is. A tenant created before
    that table existed has no row and no home domain, in which case nothing is
    marked - which is right: with nothing to compare against, calling every
    address external would be noise.
    """
    rows = _sql("SELECT domain FROM tenant_domain WHERE tenant_id = :t "
                "ORDER BY created_at LIMIT 1",
                [_p("t", tenant_id)]).get("records", [])
    return _col(rows[0], 0) if rows else None


def _admins(tenant_id):
    return _col(_sql(
        "SELECT COUNT(*) FROM seat WHERE tenant_id = :t AND role = 'admin'",
        [_p("t", tenant_id)])["records"][0], 0)


# --- which workspaces (PACK-02 C) ------------------------------------------

# A DELETED WORKSPACE IS NOT HERE (PACK-02 D). Hidden for six months, it is
# not one a seat can be given, nor one a member works in - but the rows that
# assign it are kept, and nothing below deletes them, so a restore gives back
# exactly the access there was.
_LIVE = ("SELECT workspace_id FROM workspace "
         "WHERE tenant_id = :t AND deleted_at IS NULL")


def _tenant_workspaces(tenant_id):
    return [int(_col(r, 0)) for r in _sql(
        _LIVE + " ORDER BY workspace_id", [_p("t", tenant_id)]
    ).get("records", [])]


def _checked_workspaces(tenant_id, workspace_ids):
    """The workspaces asked for, as this tenant's ids, refusing any other.
    The tenant is the token's; a number from the request is checked here."""
    if not isinstance(workspace_ids, (list, tuple)):
        raise ValueError("Name the workspaces as a list.")
    held = set(_tenant_workspaces(tenant_id))
    wanted = []
    for w in workspace_ids:
        if isinstance(w, bool):
            raise ValueError("A workspace is named by its number.")
        try:
            w = int(w)
        except (TypeError, ValueError):
            raise ValueError("A workspace is named by its number.")
        if w not in held:
            raise ValueError("This account has no workspace %d." % w)
        if w not in wanted:
            wanted.append(w)
    return wanted


def allowed_workspaces(tenant_id, email, role):
    """The workspaces this caller may work in: None for an administrator,
    who may work in every one; otherwise the set assigned to their seat,
    which may be empty.

    Read from the seat by address, as listing() marks "you": one address is
    one seat (seat.uq_email). A role from the token is what decides, as it
    does everywhere else in the API - a changed role takes effect when the
    token refreshes, and removing the seat is what takes effect at once."""
    if role == "admin":
        return None
    rows = _sql(
        """
        SELECT sw.workspace_id FROM seat s
        JOIN seat_workspace sw ON sw.seat_id = s.seat_id
         AND sw.tenant_id = s.tenant_id
        WHERE s.tenant_id = :t AND s.email = :e
          AND sw.workspace_id IN (%s)
        """ % _LIVE,
        [_p("t", tenant_id), _p("e", (email or "").strip().lower())],
    ).get("records", [])
    return {int(_col(r, 0)) for r in rows}


def set_workspaces(tenant_id, email, seat_id, workspace_ids):
    """Replace which workspaces a member's seat may see. At least one: a
    member is never left seeing nothing (decision of 23 October 2026). An
    administrator sees every workspace and has nothing to set."""
    rows = _sql("SELECT role FROM seat WHERE seat_id = :s AND tenant_id = :t",
                [_p("s", int(seat_id)), _p("t", tenant_id)]).get("records", [])
    if not rows:
        raise ValueError("No such seat.")
    if _col(rows[0], 0) == "admin":
        raise ValueError("An administrator sees every workspace; there is "
                         "nothing to choose.")
    wanted = _checked_workspaces(tenant_id, workspace_ids)
    if not wanted:
        raise ValueError("Choose at least one workspace. A member with none "
                         "would see nothing at all.")

    names, params = [], []
    for i, w in enumerate(wanted):
        names.append(":w%d" % i)
        params.append(_p("w%d" % i, w))
    # Live workspaces only: a hidden one is not on the screen to be ticked,
    # and its row is what a restore gives back.
    _sql("DELETE FROM seat_workspace WHERE tenant_id = :t AND seat_id = :s "
         "AND workspace_id NOT IN (%s) AND workspace_id IN (%s)"
         % (", ".join(names), _LIVE),
         [_p("t", tenant_id), _p("s", int(seat_id))] + params)
    for w in wanted:
        _sql("INSERT IGNORE INTO seat_workspace "
             "(tenant_id, seat_id, workspace_id, assigned_by) "
             "VALUES (:t, :s, :w, :by)",
             [_p("t", tenant_id), _p("s", int(seat_id)), _p("w", w),
              _p("by", email)])
    return {"seat_id": int(seat_id), "workspaces": wanted}


def _seat_workspaces(tenant_id):
    """Every member seat's workspaces, by seat."""
    out = {}
    for r in _sql("SELECT seat_id, workspace_id FROM seat_workspace "
                  "WHERE tenant_id = :t AND workspace_id IN (%s) "
                  "ORDER BY workspace_id" % _LIVE,
                  [_p("t", tenant_id)]).get("records", []):
        out.setdefault(int(_col(r, 0)), []).append(int(_col(r, 1)))
    return out


def _invitation_workspaces(tenant_id):
    out = {}
    for r in _sql(
            "SELECT iw.invitation_id, iw.workspace_id "
            "FROM seat_invitation_workspace iw "
            "JOIN seat_invitation i ON i.invitation_id = iw.invitation_id "
            "WHERE i.tenant_id = :t AND iw.workspace_id IN (%s) "
            "ORDER BY iw.workspace_id" % _LIVE,
            [_p("t", tenant_id)]).get("records", []):
        out.setdefault(int(_col(r, 0)), []).append(int(_col(r, 1)))
    return out


def listing(tenant_id, email):
    """Seats, open invitations, and what is left.

    Invitations are listed beside seats rather than separately, because an
    administrator counting who has access has to count both - a reserved seat
    is as unavailable as a taken one.
    """
    taken = _sql(
        """
        SELECT seat_id, email, role, invited_by, accepted_at
        FROM seat WHERE tenant_id = :t ORDER BY role, email
        """,
        [_p("t", tenant_id)],
    ).get("records", [])

    pending = _sql(
        """
        SELECT invitation_id, email, role, invited_by, created_at, expires_at
        FROM seat_invitation
        WHERE tenant_id = :t AND revoked_at IS NULL AND expires_at > NOW()
        ORDER BY email
        """,
        [_p("t", tenant_id)],
    ).get("records", [])

    bought = seats_bought(tenant_id)
    home = _home_domain(tenant_id)

    # An address outside the tenant's own domain is allowed and marked.
    #
    # Allowed because it is a real case: a firm running diligence brings in
    # outside counsel, a consultant, a client-side reviewer. Forbidding it
    # would make the workaround a shared login, which is worse.
    #
    # Marked because the abusive case looks identical - ten people at ten
    # firms on one plan - and the person who would have to explain that is the
    # administrator looking at this list.
    def external(address):
        if not home or "@" not in (address or ""):
            return False
        return address.split("@", 1)[1].lower() != home.lower()

    # Which workspaces each member sees, and each invitation will (PACK-02
    # C). An administrator's is None: every one.
    by_seat = _seat_workspaces(tenant_id)
    by_invitation = _invitation_workspaces(tenant_id)

    seats = [{
        "seat_id": _col(r, 0), "email": _col(r, 1), "role": _col(r, 2),
        "invited_by": _col(r, 3), "accepted_at": _col(r, 4),
        "you": _col(r, 1) == email,
        "external": external(_col(r, 1)),
        "workspaces": None if _col(r, 2) == "admin"
                      else by_seat.get(int(_col(r, 0)), []),
    } for r in taken]

    invitations = [{
        "invitation_id": _col(r, 0), "email": _col(r, 1), "role": _col(r, 2),
        "invited_by": _col(r, 3), "created_at": _col(r, 4),
        "expires_at": _col(r, 5),
        "external": external(_col(r, 1)),
        "workspaces": None if _col(r, 2) == "admin"
                      else by_invitation.get(int(_col(r, 0)), []),
    } for r in pending]

    return {
        "seats": seats,
        "invitations": invitations,
        "bought": bought,
        "taken": len(seats),
        "reserved": len(invitations),
        "free": max(0, bought - len(seats) - len(invitations)),
        "admins": _admins(tenant_id),
        "home_domain": home,
        "external": sum(1 for s in seats if s["external"])
                    + sum(1 for i in invitations if i["external"]),
    }


# --- inviting --------------------------------------------------------------

def invite(tenant_id, email, invitee, role, workspace_ids=None):
    """Reserve a seat and mint a token. Sending the email is the caller's job.

    Returns the token in clear, once. It is stored hashed and cannot be read
    back - if the email is lost the invitation is sent again, which is the
    same guarantee a password reset makes.

    A MEMBER'S INVITATION NAMES ITS WORKSPACES, at least one (PACK-02 C), so
    nobody arrives seeing none. An administrator's names none: they see every
    workspace. Inviting the same address again replaces the list.
    """
    invitee = (invitee or "").strip().lower()
    role = role if role in ROLES else "member"

    # ARQEDIA's own workspace hands out no invitations. A seat there decides
    # what every tenant is offered, so it is created by hand and never by a
    # link somebody was sent. signup.accept refuses the other end of this.
    if not isinstance(tenant_id, int) or tenant_id <= 0:
        raise ValueError(
            "Seats in the ARQEDIA workspace are not invited. They are "
            "created by hand.")

    if not invitee or "@" not in invitee:
        raise ValueError("That does not look like an email address.")

    # After the two refusals above, which say more about what is wrong.
    workspaces = []
    if role == "member":
        workspaces = _checked_workspaces(tenant_id, workspace_ids or [])
        if not workspaces:
            raise ValueError("Choose at least one workspace for a member to "
                             "see.")

    held = _sql("SELECT tenant_id FROM seat WHERE email = :e",
                [_p("e", invitee)]).get("records", [])
    if held:
        if _col(held[0], 0) == tenant_id:
            raise ValueError(f"{invitee} already holds a seat here.")
        # One address, one tenant. Somebody who genuinely works for two firms
        # uses two addresses, as they do everywhere else.
        raise ValueError(f"{invitee} already belongs to another workspace.")

    state = listing(tenant_id, email)
    # An invitation replacing this person's own open one does not need a free
    # seat: it is already reserved for them.
    replacing = any(i["email"] == invitee for i in state["invitations"])
    if state["free"] == 0 and not replacing:
        raise SeatsFull(
            f"All {state['bought']} seats are taken or reserved. "
            "Remove one, or change the plan.")

    token = secrets.token_urlsafe(32)
    expires = (datetime.datetime.utcnow()
               + datetime.timedelta(days=INVITE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    _sql(
        """
        INSERT INTO seat_invitation
          (tenant_id, email, role, token_hash, invited_by, expires_at)
        VALUES (:t, :e, :r, :h, :by, :exp)
        ON DUPLICATE KEY UPDATE
          tenant_id = VALUES(tenant_id), role = VALUES(role),
          token_hash = VALUES(token_hash), invited_by = VALUES(invited_by),
          created_at = NOW(), expires_at = VALUES(expires_at),
          revoked_at = NULL
        """,
        [_p("t", tenant_id), _p("e", invitee), _p("r", role),
         _p("h", _sha(token)), _p("by", email), _p("exp", expires)],
    )

    # The invitation's workspaces, replacing any an earlier invitation of
    # the same address named. Found by address: an upsert keeps the id, and
    # the address is the invitation's unique key (uq_open).
    found = _sql("SELECT invitation_id FROM seat_invitation WHERE email = :e",
                 [_p("e", invitee)]).get("records", [])
    invitation_id = int(_col(found[0], 0))
    _sql("DELETE FROM seat_invitation_workspace WHERE invitation_id = :i",
         [_p("i", invitation_id)])
    for w in workspaces:
        _sql("INSERT INTO seat_invitation_workspace "
             "(invitation_id, workspace_id) VALUES (:i, :w)",
             [_p("i", invitation_id), _p("w", w)])

    return {"token": token, "email": invitee, "role": role,
            "expires_at": expires, "workspaces": workspaces or None}


def revoke_invitation(tenant_id, invitation_id):
    _sql(
        "UPDATE seat_invitation SET revoked_at = NOW() "
        "WHERE invitation_id = :i AND tenant_id = :t AND revoked_at IS NULL",
        [_p("i", int(invitation_id)), _p("t", tenant_id)],
    )
    return {"revoked": True}


# --- changing and removing -------------------------------------------------

def set_role(tenant_id, seat_id, role):
    if role not in ROLES:
        raise ValueError("A seat is either an administrator or a member.")

    rows = _sql(
        "SELECT email, role FROM seat WHERE seat_id = :s AND tenant_id = :t",
        [_p("s", int(seat_id)), _p("t", tenant_id)],
    ).get("records", [])
    if not rows:
        raise ValueError("No such seat.")

    if _col(rows[0], 1) == "admin" and role != "admin" and _admins(tenant_id) <= 1:
        raise LastAdmin(
            "This is the only administrator. Make somebody else an "
            "administrator first, or this workspace can no longer change its "
            "own plan, brand or seats.")

    _sql("UPDATE seat SET role = :r WHERE seat_id = :s AND tenant_id = :t",
         [_p("r", role), _p("s", int(seat_id)), _p("t", tenant_id)])

    # An administrator made a member keeps every workspace there is
    # (decision of 23 October 2026): nothing they could see disappears, and
    # an administrator narrows it afterwards. INSERT IGNORE keeps what a
    # member already had.
    if _col(rows[0], 1) == "admin" and role == "member":
        _sql("INSERT IGNORE INTO seat_workspace "
             "(tenant_id, seat_id, workspace_id, assigned_by) "
             "SELECT :t, :s, workspace_id, 'made a member' FROM workspace "
             "WHERE tenant_id = :t AND deleted_at IS NULL",
             [_p("t", tenant_id), _p("s", int(seat_id))])
    return {"seat_id": int(seat_id), "role": role}


def remove(tenant_id, seat_id):
    """Free the seat. Nothing the person did is touched.

    A memorandum they generated stays, and still names them as its author -
    the record says who wrote it, and somebody leaving does not unwrite it.
    """
    rows = _sql(
        "SELECT email, role FROM seat WHERE seat_id = :s AND tenant_id = :t",
        [_p("s", int(seat_id)), _p("t", tenant_id)],
    ).get("records", [])
    if not rows:
        raise ValueError("No such seat.")

    if _col(rows[0], 1) == "admin" and _admins(tenant_id) <= 1:
        raise LastAdmin(
            "This is the only administrator. Make somebody else an "
            "administrator first.")

    _sql("DELETE FROM seat WHERE seat_id = :s AND tenant_id = :t",
         [_p("s", int(seat_id)), _p("t", tenant_id)])
    return {"removed": True, "email": _col(rows[0], 0)}


# --- accepting -------------------------------------------------------------
#
# Called by the signup function, not here: somebody accepting an invitation
# has no token yet, so the route is unauthenticated and belongs beside the
# other two that are.

def claim(email, token):
    """Turn a valid invitation into a seat. Returns the tenant it joins.

    The seat is counted at this moment and not before, so an invitation that
    was sent when a seat was free can still fail if somebody else accepted
    first. That is the correct answer, and the message says so.
    """
    email = (email or "").strip().lower()
    rows = _sql(
        """
        SELECT invitation_id, tenant_id, role, token_hash, expires_at
        FROM seat_invitation
        WHERE email = :e AND revoked_at IS NULL
        """,
        [_p("e", email)],
    ).get("records", [])
    if not rows:
        raise ValueError("That invitation is no longer open.")

    r = rows[0]
    invitation_id, tenant_id, role = _col(r, 0), _col(r, 1), _col(r, 2)

    if _sha(token) != _col(r, 3):
        raise ValueError("That invitation link is not valid.")
    if str(_col(r, 4)) < datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"):
        raise ValueError("That invitation has expired. Ask for another.")

    state = listing(tenant_id, email)
    if state["taken"] >= state["bought"]:
        raise SeatsFull(
            "Every seat is taken. Ask an administrator to free one or change "
            "the plan, then open this link again.")

    _sql(
        "INSERT INTO seat (tenant_id, email, role, invited_by) "
        "SELECT :t, :e, :r, invited_by FROM seat_invitation "
        "WHERE invitation_id = :i",
        [_p("t", tenant_id), _p("e", email), _p("r", role),
         _p("i", invitation_id)],
    )
    # The invitation's workspaces become the seat's (PACK-02 C), as the
    # signup function's accept does.
    _sql(
        "INSERT IGNORE INTO seat_workspace "
        "(tenant_id, seat_id, workspace_id, assigned_by) "
        "SELECT :t, s.seat_id, iw.workspace_id, i.invited_by "
        "FROM seat s JOIN seat_invitation i ON i.invitation_id = :i "
        "JOIN seat_invitation_workspace iw ON iw.invitation_id = :i "
        "WHERE s.tenant_id = :t AND s.email = :e",
        [_p("t", tenant_id), _p("e", email), _p("i", invitation_id)])
    _sql("DELETE FROM seat_invitation_workspace WHERE invitation_id = :i",
         [_p("i", invitation_id)])
    _sql("DELETE FROM seat_invitation WHERE invitation_id = :i",
         [_p("i", invitation_id)])

    return {"tenant_id": tenant_id, "role": role, "email": email}
