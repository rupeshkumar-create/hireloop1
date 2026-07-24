import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ComposerWaveform } from "./ComposerWaveform";

describe("ComposerWaveform", () => {
  it("renders bars with aria label for listening", () => {
    render(<ComposerWaveform level={0.5} active mode="listening" />);
    expect(screen.getByRole("img", { name: /listening/i })).toBeInTheDocument();
  });

  it("hides visually when inactive", () => {
    const { container } = render(
      <ComposerWaveform level={0} active={false} mode="listening" />,
    );
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });
});
