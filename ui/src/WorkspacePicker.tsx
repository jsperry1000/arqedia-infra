import { useEffect, useRef, useState } from "react";
import { activeName, useWorkspace } from "./workspace";

/**
 * The active workspace, in the header (PACK-01). Every screen follows it:
 * Configure, uploading, the engagements, their documents and their memoranda.
 *
 * BUILT FROM THE ACCOUNT CONTROL BESIDE IT - .account-toggle and
 * .account-menu, which are already styled for the navy bar and its panel. No
 * new CSS: a control written from reasoning in this header has gone wrong
 * before (CLAUDE.md), and this one is the same kind of thing as its
 * neighbour.
 *
 * SHOWN WHERE THERE IS SOMETHING TO DO WITH IT: more than one workspace to
 * choose between, or an administrator who may add one. A member of a tenant
 * with one workspace sees nothing new.
 *
 * EVERY WORKSPACE, FOR EVERY SEAT. Which workspaces a member is assigned is
 * Prompt 5 and is not built; until it is, the list is all of the tenant's.
 *
 * IN THE ARQEDIA WORKSPACE EACH ONE IS AN OFFERING (PACK-02): what a client
 * starts a workspace from. The list is the same; adding one is called what
 * it is.
 */
export function WorkspacePicker({ admin, curator = false, onAdd }: {
  admin: boolean;
  curator?: boolean;
  onAdd: () => void;
}) {
  const state = useWorkspace();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement | null>(null);

  // A click elsewhere or Escape puts it away, as the account's panel does.
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const name = activeName(state);
  if (state.workspaces.length === 0) return null;
  if (state.workspaces.length < 2 && !admin) return null;

  return (
    <span ref={box}>
      <button type="button" className="account-toggle"
              aria-expanded={open} aria-controls="workspace-menu"
              title="The workspace everything on screen belongs to"
              onClick={() => setOpen(!open)}>
        {name ?? "Choose a workspace"} {open ? "▴" : "▾"}
      </button>
      {open && (
        <div className="account-menu" id="workspace-menu">
          {state.workspaces.map((w) => (
            <a key={w.workspace_id}
               aria-current={w.workspace_id === state.active ? "true" : undefined}
               onClick={() => { setOpen(false); state.choose(w.workspace_id); }}>
              {w.workspace_id === state.active ? "✓ " : ""}{w.name}
            </a>
          ))}
          {admin && (
            <>
              <span className="sep" />
              <a onClick={() => { setOpen(false); onAdd(); }}>
                {curator ? "Add an offering" : "Add a workspace"}
              </a>
            </>
          )}
        </div>
      )}
    </span>
  );
}

/**
 * The same choice, where a screen needs to show it inline: ahead of the
 * Configure screen's parts, so the document types, facts and memoranda below
 * are never read as belonging to a workspace other than the one named.
 * A select of its own, styled wherever it is placed; a single workspace is
 * named rather than offered.
 */
export function WorkspaceInline() {
  const state = useWorkspace();
  if (state.workspaces.length === 0) return null;
  if (state.workspaces.length === 1) {
    return <span className="muted small">{state.workspaces[0].name}</span>;
  }
  return (
    <select aria-label="Workspace" value={state.active ?? ""}
            title="The workspace this configuration belongs to"
            onChange={(e) => state.choose(Number(e.target.value))}>
      {state.workspaces.map((w) => (
        <option key={w.workspace_id} value={w.workspace_id}>{w.name}</option>
      ))}
    </select>
  );
}
