"""
workspaces.py - an administrator deletes a workspace, and restores one
(PACK-02 D, settled 23 October 2026).

Self-contained, as billing.py and seats.py are: app.py imports this.

THE FIRST DELETE IN THE PRODUCT, so it does not delete. A workspace deleted
is HIDDEN: out of every list (config.workspaces), refused by number, not
counted against the plan, and the shares of its memoranda suspended. Its
rows, documents, memoranda and shares stay where they are for six months,
when they are removed for good - by a job that is a branch of its own and is
not built here. Until that date a restore brings it all back.

WHAT DELETING ASKS, in order (settled):

  1. what it holds     engagements, documents, memoranda, live shares - shown
                       before anything else is asked (listing)
  2. a code            emailed to the administrator, fifteen minutes, five
                       tries (request_code)
  3. its name, typed   and the code, and - where a member sees only this
                       workspace - which workspace they move to (delete)

NEVER TOUCHED: the ledger. Charges stay charged and nothing is refunded by
deleting.

NOT HERE: the ARQEDIA workspace's offerings. A client workspace records which
offering it came from and its Catalogue reads it; deleting one is a separate
question (settled: not in D). And the last workspace a tenant holds, which
is account deletion and a separate act.
"""

import hashlib
import hmac
import os
import secrets
import time

import boto3
from botocore.exceptions import ClientError

import billing
import mail

_rds = boto3.client("rds-data")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

PACK_TENANT = 0
CODE_MINUTES = 15
CODE_TRIES = 5
CODE_GAP_SECONDS = 60
KEEP_MONTHS = 6


class Refused(Exception):
    """Understood, and not possible in this state. 409."""


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


def _require_admin(tenant_id, role):
    if role != "admin":
        raise PermissionError(
            "only an administrator may delete or restore a workspace")
    if int(tenant_id) == PACK_TENANT:
        raise PermissionError(
            "an offering is not deleted here: client workspaces were started "
            "from it")


def _hash(tenant_id, workspace_id, code):
    text = "%d:%d:%s" % (int(tenant_id), int(workspace_id), code)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- reading ---------------------------------------------------------------

def _workspace(tenant_id, workspace_id):
    """One of this tenant's workspaces, live or hidden, or None. The tenant
    is the token's; a number from another tenant is not found."""
    try:
        workspace_id = int(workspace_id)
    except (TypeError, ValueError):
        raise ValueError("a workspace is named by its number")
    rows = _sql(
        "SELECT workspace_id, name, deleted_at, deleted_by, remove_after, "
        "remove_after > NOW() FROM workspace "
        "WHERE tenant_id = :t AND workspace_id = :w",
        [_p("t", tenant_id), _p("w", workspace_id)]).get("records", [])
    if not rows:
        return None
    r = rows[0]
    return {"workspace_id": int(_col(r, 0)), "name": _col(r, 1),
            "deleted_at": _col(r, 2), "deleted_by": _col(r, 3),
            "remove_after": _col(r, 4),
            "restorable": bool(_col(r, 5))}


def _counts(tenant_id, workspace_id):
    def one(table):
        rows = _sql("SELECT COUNT(*) FROM %s "
                    "WHERE tenant_id = :t AND workspace_id = :w" % table,
                    [_p("t", tenant_id), _p("w", workspace_id)]
                    ).get("records", [])
        return int(_col(rows[0], 0)) if rows else 0
    # Imported here, as app.py imports it: share.py reads the layer's
    # share_rules, and a layer nobody rebuilt must stop sharing, not this.
    import share
    return {"engagements": one("engagement"), "documents": one("document"),
            "memos": one("memo"),
            "shares": share.live_count(tenant_id, workspace_id)}


def _only_here(tenant_id, workspace_id):
    """The members, and the open invitations, who see this workspace and no
    other live one. Deleting it would leave them seeing nothing, so they are
    moved (settled: reassigned on delete)."""
    seats = _sql(
        """
        SELECT s.seat_id, s.email FROM seat s
        JOIN seat_workspace sw ON sw.seat_id = s.seat_id
         AND sw.tenant_id = s.tenant_id AND sw.workspace_id = :w
        WHERE s.tenant_id = :t AND s.role = 'member'
          AND NOT EXISTS (
            SELECT 1 FROM seat_workspace o
            JOIN workspace ow ON ow.workspace_id = o.workspace_id
             AND ow.tenant_id = o.tenant_id AND ow.deleted_at IS NULL
            WHERE o.seat_id = s.seat_id AND o.tenant_id = s.tenant_id
              AND o.workspace_id <> :w)
        ORDER BY s.email
        """,
        [_p("t", tenant_id), _p("w", workspace_id)]).get("records", [])
    invitations = _sql(
        """
        SELECT i.invitation_id, i.email FROM seat_invitation i
        JOIN seat_invitation_workspace iw ON iw.invitation_id = i.invitation_id
         AND iw.workspace_id = :w
        WHERE i.tenant_id = :t AND i.revoked_at IS NULL
          AND i.expires_at > NOW()
          AND NOT EXISTS (
            SELECT 1 FROM seat_invitation_workspace o
            JOIN workspace ow ON ow.workspace_id = o.workspace_id
             AND ow.tenant_id = :t AND ow.deleted_at IS NULL
            WHERE o.invitation_id = i.invitation_id AND o.workspace_id <> :w)
        ORDER BY i.email
        """,
        [_p("t", tenant_id), _p("w", workspace_id)]).get("records", [])
    return ([(int(_col(r, 0)), _col(r, 1)) for r in seats],
            [(int(_col(r, 0)), _col(r, 1)) for r in invitations])


def listing(tenant_id, role):
    """Every workspace, with what it holds; the deleted ones with the date
    they go and whether they can still come back."""
    _require_admin(tenant_id, role)
    rows = _sql(
        "SELECT workspace_id, name, deleted_at, deleted_by, remove_after, "
        "remove_after > NOW() FROM workspace WHERE tenant_id = :t "
        "ORDER BY workspace_id",
        [_p("t", tenant_id)]).get("records", [])
    live, hidden = [], []
    for r in rows:
        w = {"workspace_id": int(_col(r, 0)), "name": _col(r, 1)}
        if _col(r, 2) is None:
            seats, invitations = _only_here(tenant_id, w["workspace_id"])
            w.update(_counts(tenant_id, w["workspace_id"]))
            w["members_only_here"] = [e for _, e in seats]
            w["invitations_only_here"] = [e for _, e in invitations]
            live.append(w)
        else:
            w.update({"deleted_at": _col(r, 2), "deleted_by": _col(r, 3),
                      "remove_after": _col(r, 4),
                      "restorable": bool(_col(r, 5))})
            hidden.append(w)
    return {"workspaces": live, "deleted": hidden,
            "workspace_limit": billing.workspace_limit(tenant_id),
            "keep_months": KEEP_MONTHS}


# --- deleting --------------------------------------------------------------

def _live(tenant_id, workspace_id):
    found = _workspace(tenant_id, workspace_id)
    if found is None:
        return None
    if found["deleted_at"] is not None:
        raise Refused("That workspace is already deleted.")
    held = billing.workspaces_held(tenant_id)
    if held <= 1:
        raise Refused("This is your only workspace, so it cannot be deleted. "
                      "Closing the account is a separate step.")
    return found


def request_code(tenant_id, email, role, workspace_id):
    """Email the administrator a code that deleting this workspace needs.
    Returns None where the tenant has no such workspace."""
    _require_admin(tenant_id, role)
    found = _live(tenant_id, workspace_id)
    if found is None:
        return None

    recent = _sql(
        "SELECT COUNT(*) FROM workspace_deletion "
        "WHERE tenant_id = :t AND workspace_id = :w "
        "AND requested_at > NOW() - INTERVAL %d SECOND" % CODE_GAP_SECONDS,
        [_p("t", tenant_id), _p("w", found["workspace_id"])]
    ).get("records", [])
    if recent and int(_col(recent[0], 0)) > 0:
        raise Refused("A code was sent less than a minute ago. Check your "
                      "email, or ask again in a minute.")

    code = "%06d" % secrets.randbelow(1000000)
    _sql(
        "INSERT INTO workspace_deletion "
        "(tenant_id, workspace_id, requested_by, code_hash, code_expires_at) "
        "VALUES (:t, :w, :by, :h, NOW() + INTERVAL %d MINUTE)" % CODE_MINUTES,
        [_p("t", tenant_id), _p("w", found["workspace_id"]),
         _p("by", email), _p("h", _hash(tenant_id, found["workspace_id"],
                                        code))])

    subject = "Your code to delete the workspace %s" % found["name"]
    body = (
        "Somebody signed in as %s asked to delete the ARQEDIA workspace "
        "\"%s\".\n"
        "\n"
        "The code is: %s\n"
        "\n"
        "It works for %d minutes. Deleting hides the workspace at once and "
        "removes it for good after %d months; until then it can be restored "
        "under Account management, Workspaces.\n"
        "\n"
        "If this was not you, do nothing: without the code nothing is "
        "deleted. Then change your password.\n"
        "\n"
        "ARQEDIA\n"
    ) % (email, found["name"], code, CODE_MINUTES, KEEP_MONTHS)
    sent = mail.send(email, subject, body)
    print("[workspace-delete-code] tenant=%s workspace=%s sent=%s" % (
        tenant_id, found["workspace_id"], sent))
    return {"sent": sent, "minutes": CODE_MINUTES}


def delete(tenant_id, email, role, workspace_id, body):
    """Hide the workspace, after the name, the code and - where needed - the
    workspace its members move to. Returns None where the tenant has no such
    workspace.

    IN AN ORDER THAT CAN BE RUN AGAIN. Members are moved, then the shares
    suspended, then the workspace hidden and the code spent - each safe to
    repeat - so a failure part-way leaves the code good for another press,
    and never a hidden workspace whose shares still open."""
    _require_admin(tenant_id, role)
    body = body or {}
    found = _live(tenant_id, workspace_id)
    if found is None:
        return None
    ws = found["workspace_id"]

    if str(body.get("name") or "").strip() != found["name"].strip():
        raise ValueError("Type the workspace's name exactly as it is shown.")

    rows = _sql(
        "SELECT deletion_id, code_hash, tries, code_expires_at > NOW() "
        "FROM workspace_deletion WHERE tenant_id = :t AND workspace_id = :w "
        "AND deleted_at IS NULL ORDER BY deletion_id DESC LIMIT 1",
        [_p("t", tenant_id), _p("w", ws)]).get("records", [])
    if not rows:
        raise ValueError("Ask for a code first.")
    deletion_id = int(_col(rows[0], 0))
    if not _col(rows[0], 3) or int(_col(rows[0], 2)) >= CODE_TRIES:
        raise ValueError("That code has expired or been tried too often. Ask "
                         "for a new one.")
    _sql("UPDATE workspace_deletion SET tries = tries + 1 "
         "WHERE deletion_id = :d", [_p("d", deletion_id)])
    if not hmac.compare_digest(_col(rows[0], 1),
                               _hash(tenant_id, ws,
                                     str(body.get("code") or "").strip())):
        raise ValueError("That code is not right.")

    seats, invitations = _only_here(tenant_id, ws)
    target = body.get("move_members_to")
    if seats or invitations:
        if target in (None, ""):
            who = [e for _, e in seats] + [e for _, e in invitations]
            raise Refused("%s %s only this workspace. Choose the workspace "
                          "they move to." % (", ".join(who),
                                             "sees" if len(who) == 1
                                             else "see"))
        moved_to = _workspace(tenant_id, target)
        if (moved_to is None or moved_to["deleted_at"] is not None
                or moved_to["workspace_id"] == ws):
            raise ValueError("Members move to another of your workspaces.")
        target = moved_to["workspace_id"]
        for seat_id, _ in seats:
            _sql("INSERT IGNORE INTO seat_workspace "
                 "(tenant_id, seat_id, workspace_id, assigned_by) "
                 "VALUES (:t, :s, :w, :by)",
                 [_p("t", tenant_id), _p("s", seat_id), _p("w", target),
                  _p("by", email)])
        for invitation_id, _ in invitations:
            _sql("INSERT IGNORE INTO seat_invitation_workspace "
                 "(invitation_id, workspace_id) VALUES (:i, :w)",
                 [_p("i", invitation_id), _p("w", target)])
    else:
        target = None

    import share
    suspended = share.suspend_workspace(tenant_id, ws, email)

    _sql("UPDATE workspace SET deleted_at = NOW(), deleted_by = :by, "
         "remove_after = NOW() + INTERVAL %d MONTH "
         "WHERE tenant_id = :t AND workspace_id = :w AND deleted_at IS NULL"
         % KEEP_MONTHS,
         [_p("by", email), _p("t", tenant_id), _p("w", ws)])
    _sql("UPDATE workspace_deletion SET deleted_at = NOW(), "
         "members_moved_to = :m WHERE deletion_id = :d",
         [_p("m", target), _p("d", deletion_id)])

    print("[workspace-deleted] tenant=%s workspace=%s moved=%d to=%s "
          "shares=%d" % (tenant_id, ws, len(seats) + len(invitations),
                         target, suspended))
    gone = _workspace(tenant_id, ws)
    return {"workspace_id": ws, "name": found["name"],
            "remove_after": gone["remove_after"] if gone else None,
            "members_moved": [e for _, e in seats],
            "invitations_moved": [e for _, e in invitations],
            "members_moved_to": target, "shares_suspended": suspended}


# --- restoring -------------------------------------------------------------

def restore(tenant_id, email, role, workspace_id):
    """Bring a deleted workspace back, before its date, where the plan has
    room. Returns None where the tenant has no such workspace.

    Members moved away when it was deleted keep the workspace they were
    moved to as well: restoring adds, and an administrator narrows it."""
    _require_admin(tenant_id, role)
    found = _workspace(tenant_id, workspace_id)
    if found is None:
        return None
    if found["deleted_at"] is None:
        raise Refused("That workspace is not deleted.")
    if not found["restorable"]:
        raise Refused("That workspace's date has passed, so it can no longer "
                      "be restored.")
    # A deleted workspace is not counted, so its place may have been taken.
    try:
        billing.require_workspace_room(tenant_id)
    except billing.Refused:
        raise Refused("Your plan has no room for another workspace. Delete "
                      "one first, or change the plan.")

    ws = found["workspace_id"]
    import share
    lifted = share.lift_workspace(tenant_id, ws)
    _sql("UPDATE workspace SET deleted_at = NULL, deleted_by = NULL, "
         "remove_after = NULL WHERE tenant_id = :t AND workspace_id = :w",
         [_p("t", tenant_id), _p("w", ws)])
    _sql("UPDATE workspace_deletion SET restored_at = NOW(), "
         "restored_by = :by WHERE tenant_id = :t AND workspace_id = :w "
         "AND deleted_at IS NOT NULL AND restored_at IS NULL",
         [_p("by", email), _p("t", tenant_id), _p("w", ws)])
    print("[workspace-restored] tenant=%s workspace=%s shares=%d" % (
        tenant_id, ws, lifted))
    return {"workspace_id": ws, "name": found["name"],
            "shares_restored": lifted}
