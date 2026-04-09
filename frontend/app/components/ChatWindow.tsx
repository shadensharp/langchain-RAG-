"use client";

import React, { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { useSearchParams } from "next/navigation";
import Image from "next/image";
import { v4 as uuidv4 } from "uuid";

import { EmptyState } from "./EmptyState";
import { ChatMessageBubble, Message } from "./ChatMessageBubble";
import { AutoResizeTextarea } from "./AutoResizeTextarea";
import { Source } from "./SourceBubble";
import { marked, Renderer } from "marked";
import hljs from "highlight.js";
import "highlight.js/styles/gradient-dark.css";

import "react-toastify/dist/ReactToastify.css";
import { toast } from "react-toastify";
import {
  Heading,
  Flex,
  IconButton,
  InputGroup,
  InputRightElement,
  Spinner,
  Text,
  Button,
} from "@chakra-ui/react";
import { ArrowUpIcon } from "@chakra-ui/icons";
import { Select, Link } from "@chakra-ui/react";
import { apiBaseUrl } from "../utils/constants";

const MODEL_TYPES = ["openai_gpt_3_5_turbo"];
const defaultLlmValue = MODEL_TYPES[0];
const CLIENT_ID_STORAGE_KEY = "chat-langchain:client-id:v1";
const CONVERSATION_ID_STORAGE_KEY = "chat-langchain:conversation-id:v1";

type ApprovedAnswerPreference = {
  answer: string;
  notes: string;
};

type AdjustmentFeedback = {
  comment: string;
  answer?: string;
};

type ResponsePreferences = {
  approved_answer?: ApprovedAnswerPreference;
  adjustment_feedback: AdjustmentFeedback[];
};

type SessionMessage = {
  id: string;
  role: "system" | "user" | "assistant" | "function";
  rawContent: string;
  runId?: string;
  sources?: Source[];
  status?: "pending" | "complete";
  feedback?: {
    rating: "good" | "bad";
    comment?: string;
  };
};

type SessionResponse = {
  client_id: string;
  conversation_id: string;
  response_preferences: ResponsePreferences;
  messages: SessionMessage[];
};

type ChatApiResponse = {
  client_id: string;
  conversation_id: string;
  response_preferences: ResponsePreferences;
  user_message: SessionMessage;
  assistant_message: SessionMessage;
};

type FeedbackResponse = {
  message_id: string;
  response_preferences: ResponsePreferences;
  message: SessionMessage;
};

const createDefaultResponsePreferences = (): ResponsePreferences => ({
  adjustment_feedback: [],
});

const hasRememberedPreferences = (preferences: ResponsePreferences) =>
  Boolean(
    preferences.approved_answer || preferences.adjustment_feedback.length > 0,
  );

const renderMarkdown = (content: string) => {
  const renderer = new Renderer();
  renderer.paragraph = (text) => text + "\n";
  renderer.list = (text) => `${text}\n\n`;
  renderer.listitem = (text) => `\n- ${text}`;
  renderer.code = (code, language) => {
    const validLanguage = hljs.getLanguage(language || "")
      ? language || "plaintext"
      : "plaintext";
    const highlightedCode = hljs.highlight(code, {
      language: validLanguage,
    }).value;
    return `<pre class="highlight bg-gray-700" style="padding: 5px; border-radius: 5px; overflow: auto; overflow-wrap: anywhere; white-space: pre-wrap; max-width: 100%; display: block; line-height: 1.2"><code class="${validLanguage}" style="color: #d6e2ef; font-size: 12px;">${highlightedCode}</code></pre>`;
  };

  return marked.parse(content, { renderer }) as string;
};

const isSource = (value: unknown): value is Source => {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  return (
    typeof (value as Source).citation === "number" &&
    typeof (value as Source).title === "string" &&
    typeof (value as Source).url === "string" &&
    typeof (value as Source).location === "string" &&
    typeof (value as Source).excerpt === "string"
  );
};

const normalizeResponsePreferences = (value: unknown): ResponsePreferences => {
  if (typeof value !== "object" || value === null) {
    return createDefaultResponsePreferences();
  }

  const candidate = value as ResponsePreferences;
  return {
    approved_answer:
      candidate.approved_answer &&
      typeof candidate.approved_answer.answer === "string" &&
      typeof candidate.approved_answer.notes === "string"
        ? candidate.approved_answer
        : undefined,
    adjustment_feedback: Array.isArray(candidate.adjustment_feedback)
      ? candidate.adjustment_feedback.filter(
          (item) =>
            typeof item === "object" &&
            item !== null &&
            typeof (item as AdjustmentFeedback).comment === "string" &&
            ((item as AdjustmentFeedback).answer === undefined ||
              typeof (item as AdjustmentFeedback).answer === "string"),
        )
      : [],
  };
};

const normalizeSessionMessage = (value: unknown): SessionMessage | null => {
  if (typeof value !== "object" || value === null) {
    return null;
  }

  const candidate = value as SessionMessage;
  if (typeof candidate.id !== "string" || typeof candidate.role !== "string") {
    return null;
  }

  const rawContent =
    typeof candidate.rawContent === "string"
      ? candidate.rawContent
      : typeof (candidate as { content?: unknown }).content === "string"
        ? String((candidate as { content?: unknown }).content)
        : "";

  const sources = Array.isArray(candidate.sources)
    ? candidate.sources.filter(isSource)
    : [];

  return {
    id: candidate.id,
    role: candidate.role,
    rawContent,
    runId: typeof candidate.runId === "string" ? candidate.runId : undefined,
    sources,
    status: candidate.status === "pending" ? "pending" : "complete",
    feedback:
      candidate.feedback &&
      (candidate.feedback.rating === "good" ||
        candidate.feedback.rating === "bad")
        ? candidate.feedback
        : undefined,
  };
};

const hydrateMessage = (message: SessionMessage): Message => ({
  id: message.id,
  role: message.role,
  rawContent: message.rawContent,
  content:
    message.role === "assistant"
      ? renderMarkdown(message.rawContent).trim()
      : message.rawContent,
  runId: message.runId,
  sources: message.sources,
  feedback: message.feedback,
  status: message.status ?? "complete",
});

const readStoredId = (key: string, fallbackValue: string) => {
  if (typeof window === "undefined") {
    return fallbackValue;
  }

  try {
    const storedValue = window.localStorage.getItem(key);
    if (storedValue && storedValue.trim()) {
      return storedValue;
    }
    window.localStorage.setItem(key, fallbackValue);
  } catch (error) {
    console.error(`Failed to access localStorage key ${key}:`, error);
  }

  return fallbackValue;
};

const persistStoredId = (key: string, value: string) => {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(key, value);
};

export function ChatWindow(props: { conversationId: string }) {
  const searchParams = useSearchParams();
  const messageContainerRef = useRef<HTMLDivElement | null>(null);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionIsLoading, setSessionIsLoading] = useState(true);
  const [clientId, setClientId] = useState("");
  const [activeConversationId, setActiveConversationId] = useState(
    props.conversationId,
  );
  const [llm, setLlm] = useState(
    searchParams.get("llm") ?? "openai_gpt_3_5_turbo",
  );
  const [llmIsLoading, setLlmIsLoading] = useState(true);
  const [responsePreferences, setResponsePreferences] =
    useState<ResponsePreferences>(createDefaultResponsePreferences);

  useEffect(() => {
    setLlm(searchParams.get("llm") ?? defaultLlmValue);
    setLlmIsLoading(false);
  }, [searchParams]);

  useEffect(() => {
    const resolvedClientId = readStoredId(CLIENT_ID_STORAGE_KEY, uuidv4());
    const resolvedConversationId = readStoredId(
      CONVERSATION_ID_STORAGE_KEY,
      props.conversationId,
    );
    setClientId(resolvedClientId);
    setActiveConversationId(resolvedConversationId);
  }, [props.conversationId]);

  useEffect(() => {
    if (!clientId || !activeConversationId) {
      return;
    }

    let cancelled = false;
    setSessionIsLoading(true);

    const loadSession = async () => {
      try {
        const url = new URL(`${apiBaseUrl}/api/session`);
        url.searchParams.set("client_id", clientId);
        url.searchParams.set("conversation_id", activeConversationId);

        const response = await fetch(url.toString());
        if (!response.ok) {
          throw new Error(`Unable to load session (${response.status})`);
        }

        const data = (await response.json()) as SessionResponse;
        if (cancelled) {
          return;
        }

        const normalizedMessages = Array.isArray(data.messages)
          ? data.messages
              .map(normalizeSessionMessage)
              .filter((message): message is SessionMessage => message !== null)
              .map(hydrateMessage)
          : [];

        setMessages(normalizedMessages);
        setResponsePreferences(
          normalizeResponsePreferences(data.response_preferences),
        );
      } catch (error) {
        console.error("Failed to load session:", error);
        if (!cancelled) {
          toast.error(
            error instanceof Error
              ? error.message
              : "Failed to load the saved conversation.",
          );
        }
      } finally {
        if (!cancelled) {
          setSessionIsLoading(false);
        }
      }
    };

    void loadSession();

    return () => {
      cancelled = true;
    };
  }, [clientId, activeConversationId]);

  const sendMessage = async (message?: string) => {
    if (messageContainerRef.current) {
      messageContainerRef.current.classList.add("grow");
    }
    if (isLoading || sessionIsLoading || !clientId || !activeConversationId) {
      return;
    }

    const messageValue = message ?? input;
    if (messageValue === "") return;

    let userMessageIndex: number | null = null;
    let assistantMessageIndex: number | null = null;
    const placeholderId = Math.random().toString();
    const temporaryUserId = Math.random().toString();

    flushSync(() => {
      setInput("");
      setMessages((prevMessages) => {
        userMessageIndex = prevMessages.length;
        assistantMessageIndex = prevMessages.length + 1;
        return [
          ...prevMessages,
          { id: temporaryUserId, content: messageValue, role: "user" },
          {
            id: placeholderId,
            content: "Thinking...",
            rawContent: "Thinking...",
            role: "assistant",
            status: "pending",
          },
        ];
      });
      setIsLoading(true);
    });

    try {
      const llmDisplayName = llm ?? defaultLlmValue;
      const response = await fetch(`${apiBaseUrl}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          client_id: clientId,
          conversation_id: activeConversationId,
          question: messageValue,
          llm: llmDisplayName,
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `Request failed (${response.status})`);
      }

      const data = (await response.json()) as ChatApiResponse;
      const userMessage = normalizeSessionMessage(data.user_message);
      const assistantMessage = normalizeSessionMessage(data.assistant_message);

      if (userMessage === null || assistantMessage === null) {
        throw new Error("Backend returned an invalid message payload.");
      }

      setResponsePreferences(
        normalizeResponsePreferences(data.response_preferences),
      );

      setMessages((prevMessages) => {
        const nextMessages = [...prevMessages];

        if (
          userMessageIndex !== null &&
          nextMessages[userMessageIndex]?.role === "user"
        ) {
          nextMessages[userMessageIndex] = {
            ...nextMessages[userMessageIndex],
            id: userMessage.id,
            rawContent: userMessage.rawContent,
          };
        }

        const hydratedAssistantMessage = hydrateMessage(assistantMessage);
        if (
          assistantMessageIndex !== null &&
          nextMessages[assistantMessageIndex]?.role === "assistant"
        ) {
          nextMessages[assistantMessageIndex] = hydratedAssistantMessage;
        } else {
          nextMessages.push(hydratedAssistantMessage);
        }

        return nextMessages;
      });
      setIsLoading(false);
    } catch (e) {
      setMessages((prevMessages) =>
        prevMessages.filter(
          (chatMessage) =>
            chatMessage.id !== placeholderId && chatMessage.id !== temporaryUserId,
        ),
      );
      setIsLoading(false);
      setInput(messageValue);
      console.error("Error sending message:", e);
      toast.error(
        e instanceof Error
          ? e.message
          : "Request failed. Check backend and try again.",
      );
    }
  };

  const sendInitialQuestion = async (question: string) => {
    await sendMessage(question);
  };

  const insertUrlParam = (key: string, value?: string) => {
    if (window.history.pushState) {
      const params = new URLSearchParams(window.location.search);
      params.set(key, value ?? "");
      const newUrl =
        window.location.protocol +
        "//" +
        window.location.host +
        window.location.pathname +
        "?" +
        params.toString();
      window.history.pushState({ path: newUrl }, "", newUrl);
    }
  };

  const applyPositiveFeedback = async (messageId: string) => {
    const response = await fetch(`${apiBaseUrl}/api/message_feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        client_id: clientId,
        message_id: messageId,
        rating: "good",
      }),
    });
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || `Feedback failed (${response.status})`);
    }

    const data = (await response.json()) as FeedbackResponse;
    setResponsePreferences(
      normalizeResponsePreferences(data.response_preferences),
    );
    setMessages((prevMessages) =>
      prevMessages.map((message) =>
        message.id === messageId
          ? {
              ...message,
              feedback: {
                rating: "good",
              },
            }
          : message,
      ),
    );
  };

  const applyNegativeFeedback = async (messageId: string, comment: string) => {
    const response = await fetch(`${apiBaseUrl}/api/message_feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        client_id: clientId,
        message_id: messageId,
        rating: "bad",
        comment,
      }),
    });
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || `Feedback failed (${response.status})`);
    }

    const data = (await response.json()) as FeedbackResponse;
    setResponsePreferences(
      normalizeResponsePreferences(data.response_preferences),
    );
    setMessages((prevMessages) =>
      prevMessages.map((message) =>
        message.id === messageId
          ? {
              ...message,
              feedback: {
                rating: "bad",
                comment,
              },
            }
          : message,
      ),
    );
  };

  const resetStyleMemory = async () => {
    if (!clientId) {
      return;
    }

    const response = await fetch(
      `${apiBaseUrl}/api/response_preferences/${clientId}`,
      {
        method: "DELETE",
      },
    );
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || `Reset failed (${response.status})`);
    }

    const data = (await response.json()) as {
      response_preferences: ResponsePreferences;
    };
    setResponsePreferences(
      normalizeResponsePreferences(data.response_preferences),
    );
    toast.success("Style memory cleared.");
  };

  const startNewConversation = () => {
    const nextConversationId = uuidv4();
    persistStoredId(CONVERSATION_ID_STORAGE_KEY, nextConversationId);
    setActiveConversationId(nextConversationId);
    setMessages([]);
    setInput("");
  };

  const rememberedPreferencesAreActive =
    hasRememberedPreferences(responsePreferences);

  return (
    <div className="flex flex-col items-center p-8 rounded grow max-h-full">
      <Flex
        direction={"column"}
        alignItems={"center"}
        marginTop={messages.length > 0 ? "" : "64px"}
      >
        <Heading
          fontSize={messages.length > 0 ? "2xl" : "3xl"}
          fontWeight={"medium"}
          mb={1}
          color={"white"}
        >
          Chat LangChain
        </Heading>
        {messages.length > 0 ? (
          <Text fontSize="sm" mb={1} color={"gray.300"} textAlign={"center"}>
            `Good` keeps the current response style. `Bad` stores written
            feedback on the backend and adjusts later answers. `Trace` shows the
            linked source pages and retrieved excerpts behind the answer.
          </Text>
        ) : (
          <Heading
            fontSize="xl"
            fontWeight={"normal"}
            color={"white"}
            marginTop={"10px"}
            textAlign={"center"}
          >
            Ask me anything about LangChain&apos;s{" "}
            <Link href="https://python.langchain.com/" color={"blue.200"}>
              Python documentation!
            </Link>
          </Heading>
        )}
        <div className="text-white flex flex-wrap items-center justify-center mt-4 gap-3">
          <div className="flex items-center mb-2">
            <span className="shrink-0 mr-2">Powered by</span>
            {llmIsLoading ? (
              <Spinner className="my-2"></Spinner>
            ) : (
              <Select
                value={llm}
                onChange={(e) => {
                  insertUrlParam("llm", e.target.value);
                  setLlm(e.target.value);
                }}
                width={"240px"}
              >
                <option value="openai_gpt_3_5_turbo">Qwen Turbo</option>
              </Select>
            )}
          </div>
          <div className="flex items-center gap-2 mb-2">
            <Button size="xs" variant="outline" onClick={startNewConversation}>
              New Chat
            </Button>
            {rememberedPreferencesAreActive && (
              <>
                <Text fontSize="sm" color="green.200">
                  Backend style memory is active.
                </Text>
                <Button
                  size="xs"
                  variant="outline"
                  onClick={() => {
                    void resetStyleMemory().catch((error) => {
                      console.error("Failed to reset style memory:", error);
                      toast.error(
                        error instanceof Error
                          ? error.message
                          : "Failed to reset style memory.",
                      );
                    });
                  }}
                >
                  Reset Style Memory
                </Button>
              </>
            )}
          </div>
        </div>
      </Flex>
      <div
        className="flex flex-col-reverse w-full mb-2 overflow-auto"
        ref={messageContainerRef}
      >
        {sessionIsLoading ? (
          <div className="w-full flex justify-center py-10">
            <Spinner color="white" />
          </div>
        ) : messages.length > 0 ? (
          [...messages].reverse().map((message) => (
            <ChatMessageBubble
              key={message.id}
              message={{ ...message }}
              onApproveResponse={applyPositiveFeedback}
              onRejectResponse={applyNegativeFeedback}
            />
          ))
        ) : (
          <EmptyState onChoice={sendInitialQuestion} />
        )}
      </div>
      <InputGroup size="md" alignItems={"center"}>
        <AutoResizeTextarea
          value={input}
          maxRows={5}
          marginRight={"56px"}
          placeholder="Example: What does RunnablePassthrough.assign() do?"
          color={"white"}
          bg={"rgba(255, 255, 255, 0.06)"}
          borderColor={"rgb(58, 58, 61)"}
          _placeholder={{ color: "rgba(255, 255, 255, 0.55)" }}
          _focus={{
            color: "white",
            bg: "rgba(255, 255, 255, 0.08)",
            borderColor: "blue.400",
          }}
          _hover={{
            borderColor: "rgb(80, 80, 84)",
          }}
          spellCheck={false}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void sendMessage();
            } else if (e.key === "Enter" && e.shiftKey) {
              e.preventDefault();
              setInput(input + "\n");
            }
          }}
        />
        <InputRightElement h="full">
          <IconButton
            colorScheme="blue"
            rounded={"full"}
            aria-label="Send"
            icon={isLoading ? <Spinner /> : <ArrowUpIcon />}
            type="submit"
            isDisabled={sessionIsLoading}
            onClick={(e) => {
              e.preventDefault();
              void sendMessage();
            }}
          />
        </InputRightElement>
      </InputGroup>

      {messages.length === 0 ? (
        <footer className="flex justify-center absolute bottom-8">
          <a
            href="https://github.com/langchain-ai/chat-langchain"
            target="_blank"
            rel="noreferrer"
            className="text-white flex items-center"
          >
            <Image
              src="/images/github-mark.svg"
              className="h-4 mr-1"
              alt=""
              width={16}
              height={16}
            />
            <span>View Source</span>
          </a>
        </footer>
      ) : (
        ""
      )}
    </div>
  );
}
