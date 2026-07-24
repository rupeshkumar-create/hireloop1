import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CareerCallConsent } from "./CareerCallConsent";
import { InThreadCallBanner } from "./InThreadCallBanner";

afterEach(() => cleanup());

describe("Career call in-thread smoke", () => {
  it("consent confirm and cancel work", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<CareerCallConsent onConfirm={onConfirm} onCancel={onCancel} />);
    expect(screen.getByText(/15-min call with aarya/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /start call/i }));
    expect(onConfirm).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: /not now/i }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("banner shows career call status", () => {
    render(<InThreadCallBanner secondsLeft={12 * 60 + 41} />);
    expect(screen.getByText(/career call · 12:41 left/i)).toBeInTheDocument();
    expect(screen.getByText(/same chat thread/i)).toBeInTheDocument();
  });
});
