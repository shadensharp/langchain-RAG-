"use client";

import React, { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { useSearchParams } from "next/navigation";
import Image from "next/image";
import { RemoteRunnable } from "@langchain/core/runnables/remote";

import { EmptyState } from "./EmptyState";
import { ChatMessageBubble, Message } from "./ChatMessageBubble";
import { AutoResizeTextarea } from "./AutoResizeTextarea";
import { marked } from "marked";
import { Renderer } from "marked";
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
} from "@chakra-ui/react";
import { ArrowUpIcon } from "@chakra-ui/icons";
import { Select, Link } from "@chakra-ui/react";
import { Source } from "./SourceBubble";
import { apiBaseUrl } from "../utils/constants";

const MODEL_TYPES = ["openai_gpt_3_5_turbo"];

const defaultLlmValue = MODEL_TYPES[0];

export function ChatWindow(props: { conversationId: string }) {
  const conversationId = props.conversationId;

  const searchParams = useSearchParams();

  const messageContainerRef = useRef<HTMLDivElement | null>(null);
  const [messages, setMessages] = useState<Array<Message>>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [llm, setLlm] = useState(
    searchParams.get("llm") ?? "openai_gpt_3_5_turbo",
  );
  const [llmIsLoading, setLlmIsLoading] = useState(true);

  useEffect(() => {
    setLlm(searchParams.get("llm") ?? defaultLlmValue);
    setLlmIsLoading(false);
  }, [searchParams]);

  const [chatHistory, setChatHistory] = useState<
    { human: string; ai: string }[]
  >([]);

  const sendMessage = async (message?: string) => {
    if (messageContainerRef.current) {
      messageContainerRef.current.classList.add("grow");
    }
    if (isLoading) {
      return;
    }
    const messageValue = message ?? input;
    if (messageValue === "") return;
    let messageIndex: number | null = null;
    const placeholderId = Math.random().toString();
    flushSync(() => {
      setInput("");
      setMessages((prevMessages) => {
        messageIndex = prevMessages.length + 1;
        return [
          ...prevMessages,
          { id: Math.random().toString(), content: messageValue, role: "user" },
          { id: placeholderId, content: "Thinking...", role: "assistant" },
        ];
      });
      setIsLoading(true);
    });

    let accumulatedMessage = "";
    let runId: string | undefined = undefined;
    let sources: Source[] | undefined = undefined;

    let renderer = new Renderer();
    renderer.paragraph = (text) => {
      return text + "\n";
    };
    renderer.list = (text) => {
      return `${text}\n\n`;
    };
    renderer.listitem = (text) => {
      return `\n- ${text}`;
    };
    renderer.code = (code, language) => {
      const validLanguage = hljs.getLanguage(language || "")
        ? language
        : "plaintext";
      const highlightedCode = hljs.highlight(
        validLanguage || "plaintext",
        code,
      ).value;
      return `<pre class="highlight bg-gray-700" style="padding: 5px; border-radius: 5px; overflow: auto; overflow-wrap: anywhere; white-space: pre-wrap; max-width: 100%; display: block; line-height: 1.2"><code class="${language}" style="color: #d6e2ef; font-size: 12px; ">${highlightedCode}</code></pre>`;
    };
    marked.setOptions({ renderer });
    try {
      const remoteChain = new RemoteRunnable({
        url: apiBaseUrl + "/chat",
        options: { timeout: 180000 },
      });
      const llmDisplayName = llm ?? "openai_gpt_3_5_turbo";

      // Use invoke() for non-streaming backends (e.g. Qwen with streaming=False).
      // streamLog does not reliably yield output when LLM is non-streaming.
      const invokeResult = await remoteChain.invoke(
        {
          question: messageValue,
          chat_history: chatHistory,
        },
        {
          configurable: { llm: llmDisplayName },
          tags: ["model:" + llmDisplayName],
          metadata: {
            conversation_id: conversationId,
            llm: llmDisplayName,
          },
        },
      );
      accumulatedMessage =
        typeof invokeResult === "string"
          ? invokeResult
          : String(invokeResult ?? "");
      const parsedResult = marked.parse(accumulatedMessage);

      setMessages((prevMessages) => {
        const newMessages = [...prevMessages];
        const idx =
          messageIndex !== null && newMessages[messageIndex] !== undefined
            ? messageIndex
            : newMessages.length;
        if (newMessages[idx]?.role === "assistant") {
          newMessages[idx] = {
            ...newMessages[idx],
            content: parsedResult.trim(),
            runId: runId,
            sources: sources,
          };
        } else {
          newMessages.push({
            id: Math.random().toString(),
            content: parsedResult.trim(),
            runId: runId,
            sources: sources,
            role: "assistant",
          });
        }
        return newMessages;
      });

      setChatHistory((prevChatHistory) => [
        ...prevChatHistory,
        { human: messageValue, ai: accumulatedMessage },
      ]);
      setIsLoading(false);
    } catch (e) {
      setMessages((prevMessages) =>
        prevMessages.filter((message) => message.id !== placeholderId),
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
      const searchParams = new URLSearchParams(window.location.search);
      searchParams.set(key, value ?? "");
      const newurl =
        window.location.protocol +
        "//" +
        window.location.host +
        window.location.pathname +
        "?" +
        searchParams.toString();
      window.history.pushState({ path: newurl }, "", newurl);
    }
  };

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
          Chat LangChain 🦜🔗
        </Heading>
        {messages.length > 0 ? (
          <Heading fontSize="md" fontWeight={"normal"} mb={1} color={"white"}>
            We appreciate feedback!
          </Heading>
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
        <div className="text-white flex flex-wrap items-center mt-4">
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
        </div>
      </Flex>
      <div
        className="flex flex-col-reverse w-full mb-2 overflow-auto"
        ref={messageContainerRef}
      >
        {messages.length > 0 ? (
          [...messages]
            .reverse()
            .map((m, index) => (
              <ChatMessageBubble
                key={m.id}
                message={{ ...m }}
                aiEmoji="🦜"
                isMostRecent={index === 0}
                messageCompleted={!isLoading}
              ></ChatMessageBubble>
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
          placeholder="What does RunnablePassthrough.assign() do?"
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
              sendMessage();
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
            onClick={(e) => {
              e.preventDefault();
              sendMessage();
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
