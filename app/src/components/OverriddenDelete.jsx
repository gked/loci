import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useI18n } from "../lib/I18nProvider.jsx";
import { deleteAgain, getOverriddenDelete } from "../lib/api.js";

// Shown on a node that was deleted on one computer and edited on another: the
// edit won, so the node is back. Offers the delete again. It disappears on its
// own as soon as the node changes again.
export function OverriddenDelete({ uid, onDeleted }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { data } = useQuery({
    queryKey: ["overridden-delete", uid],
    queryFn: () => getOverriddenDelete(uid),
  });
  if (!data?.overridden) return null;

  const remove = async () => {
    setBusy(true);
    setError("");
    try {
      await deleteAgain(uid);
      queryClient.invalidateQueries();
      onDeleted?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="overridden-delete" data-testid="overridden-delete" role="alert">
      <span data-testid="overridden-delete-text">
        {t("This note was deleted on another computer, but an edit kept it.")}
      </span>
      <button onClick={remove} disabled={busy} data-testid="overridden-delete-again" className="t-btn">
        {t("delete again")}
      </button>
      {error && <span data-testid="overridden-delete-error">{error}</span>}
    </div>
  );
}
