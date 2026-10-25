import { useNavigate } from "react-router-dom";
import { useWorkspace } from "./workspace";
import { PLANS } from "./upgrade";

/**
 * The active workspace, at the head of the rail (PACK-01). Every screen
 * follows it: Configure, uploading, the engagements, their documents and
 * their memoranda.
 *
 * ON THE RAIL, NOT IN THE HEADER (25 October 2026). It was a toggle beside
 * the account name, in the navy bar's small white text, and read as part of
 * the masthead: the one choice that decides what every screen shows was the
 * easiest thing on screen to miss. Here it is the first thing on the rail,
 * every workspace listed beneath its heading, the active one bold and ticked.
 *
 * LISTED EVEN WHEN THERE IS ONE. Since PACK-02 C one workspace may be one of
 * several the tenant holds, and this is where a member reads which.
 *
 * A MEMBER'S LIST IS THEIR OWN (PACK-02 C): /settings names only the
 * workspaces assigned to them. An administrator's is every one.
 *
 * IN THE ARQEDIA WORKSPACE EACH ONE IS AN OFFERING (PACK-02): what a client
 * starts a workspace from. The list is the same; adding one is called what
 * it is.
 */
export function WorkspaceRail({ admin, curator = false, onAdd }: {
  admin: boolean;
  curator?: boolean;
  onAdd: () => void;
}) {
  const state = useWorkspace();
  const navigate = useNavigate();
  if (state.workspaces.length === 0) return null;

  return (
    <div className="rail-workspaces" role="group" aria-label="Workspace">
      <span className="rail-head"
            title="The workspace everything on screen belongs to">
        Workspace
      </span>
      {state.workspaces.map((w) => {
        const on = w.workspace_id === state.active;
        return (
          <a key={w.workspace_id} className={on ? "ws on" : "ws"}
             aria-current={on ? "true" : undefined}
             onClick={() => { if (!on) state.choose(w.workspace_id); }}>
            <span className="tick" aria-hidden="true">{on ? "✓" : ""}</span>
            {w.name}
          </a>
        );
      })}
      {/* AT THE PLAN'S LIMIT (PACK-02) the same place says so and goes to
          the plan table, as a full seat count does. The server refuses a
          workspace past it whatever this shows. */}
      {admin && (state.room ? (
        <a className="ws ws-add" onClick={onAdd}>
          <span className="tick" aria-hidden="true">+</span>
          {curator ? "Add an offering" : "Add a workspace"}
        </a>
      ) : (
        <a className="ws ws-add" onClick={() => navigate(PLANS)}>
          <span className="tick" aria-hidden="true" />
          Your plan holds {state.limit}{" "}
          {state.limit === 1 ? "workspace" : "workspaces"} &middot; see plans
        </a>
      ))}
    </div>
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
