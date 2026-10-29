import React, { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import AdminPanel from "./AdminPanel.jsx";
import ConnectPrompt from "./ConnectPrompt.jsx";
import "./admin.css";

/**
 * Ponto único de integração com o App:
 *   <AdminHost actions={pendingActions} onDismiss={...} onConnected={...} />
 *
 * Renderiza num portal (document.body), então não depende do layout do HUD nem
 * das cenas, e não é afetado por transform/filter dos contêineres.
 * Atalho do painel escondido: Alt + Shift + A.
 */
export default function AdminHost({ actions, onDismiss, onConnected }) {
  const [adminOpen, setAdminOpen] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      if (e.altKey && e.shiftKey && e.code === "KeyA") {
        e.preventDefault();
        setAdminOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const close = useCallback(() => setAdminOpen(false), []);

  return createPortal(
    <>
      {!adminOpen && (
        <ConnectPrompt actions={actions} onDismiss={onDismiss} onConnected={onConnected} onOpenAdmin={() => setAdminOpen(true)} />
      )}
      <AdminPanel open={adminOpen} onClose={close} />
    </>,
    document.body,
  );
}
