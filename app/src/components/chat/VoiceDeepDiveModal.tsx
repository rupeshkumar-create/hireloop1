"use client";

import { Modal } from "@/components/ui";
import { VoiceSession } from "@/app/voice/VoiceSession";

type VoiceDeepDiveModalProps = {
  open: boolean;
  onClose: () => void;
  candidateName?: string;
};

export function VoiceDeepDiveModal({
  open,
  onClose,
  candidateName,
}: VoiceDeepDiveModalProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="15-min call with Aarya"
      description="Same chat thread — your Matches stay in the left panel."
      size="lg"
      className="max-h-[min(720px,92vh)] overflow-y-auto"
    >
      <VoiceSession
        candidateName={candidateName}
        embedded
        onComplete={onClose}
      />
    </Modal>
  );
}
