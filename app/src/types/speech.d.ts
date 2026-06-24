/**
 * Web Speech API type declarations.
 *
 * TypeScript's DOM lib includes SpeechSynthesis but omits SpeechRecognition
 * (it's still a non-standard Chrome/webkit extension in many lib versions).
 * We declare the minimum surface we actually use.
 */

interface SpeechRecognitionResultItem {
  readonly transcript: string;
  readonly confidence: number;
}

interface SpeechRecognitionResult {
  readonly isFinal: boolean;
  readonly length: number;
  item(index: number): SpeechRecognitionResultItem;
  [index: number]: SpeechRecognitionResultItem;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string;
  readonly message: string;
}

declare class SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;

  onresult:  ((event: SpeechRecognitionEvent) => void)      | null;
  onerror:   ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend:     (() => void)                                    | null;
  onstart:   (() => void)                                    | null;

  start(): void;
  stop():  void;
  abort(): void;
}

interface Window {
  SpeechRecognition?:        typeof SpeechRecognition;
  webkitSpeechRecognition?:  typeof SpeechRecognition;
}
