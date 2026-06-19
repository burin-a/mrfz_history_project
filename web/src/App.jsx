import "./index.css"
import Sidebar from "./components/Sidebar"
import MessageList from "./components/MessageList"
import InputArea from "./components/InputArea"
import MusicBox from "./components/MusicBox"
import UpdateOverlay from "./components/UpdateOverlay"

function App() {
  return (
    <div className="flex h-screen text-white overflow-hidden" style={{ background: "#0a0a1a" }}>
      {/* Content layer */}
      <div className="relative z-10 flex h-full w-full">
        <Sidebar />
        <main className="flex-1 flex flex-col min-w-0 relative overflow-hidden">
          {/* Background image blended into chat area */}
          <div className="absolute inset-0 pointer-events-none" style={{ background: "#0a0a1a" }}>
            <img
              src="/Babel-Rhodes Island.png"
              alt=""
              className="w-full h-full object-cover"
              style={{ filter: "grayscale(1) brightness(0.4)", mixBlendMode: "multiply" }}
            />
          </div>
          <MessageList />
          <InputArea />
        </main>
      </div>

      {/* Music box overlay */}
      <MusicBox />

      {/* 知识库更新覆盖层（更新进行中 / 完成提示刷新） */}
      <UpdateOverlay />
    </div>
  )
}

export default App
