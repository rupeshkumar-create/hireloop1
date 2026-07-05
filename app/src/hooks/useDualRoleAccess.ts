"use client";

import { useEffect, useState } from "react";
import { canSwitchRoles, fetchAuthMe } from "@/lib/api/auth";

type DualRoleAccess = {
  canSwitch: boolean;
  loading: boolean;
};

export function useDualRoleAccess(): DualRoleAccess {
  const [state, setState] = useState<DualRoleAccess>({
    canSwitch: false,
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;
    fetchAuthMe()
      .then((me) => {
        if (!cancelled) {
          setState({ canSwitch: canSwitchRoles(me), loading: false });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ canSwitch: false, loading: false });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
