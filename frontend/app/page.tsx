"use client";

import { useState } from "react";
import { v4 as uuidv4 } from "uuid";
import { ChatWindow } from "./components/ChatWindow";
import { ToastContainer } from "react-toastify";

import { ChakraProvider } from "@chakra-ui/react";

export default function Home() {
  const [conversationId] = useState(() => uuidv4());

  return (
    <ChakraProvider>
      <ToastContainer />
      <ChatWindow conversationId={uuidv4()}></ChatWindow>
    </ChakraProvider>
  );
}
