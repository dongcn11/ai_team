---
stepsCompleted: [1, 2, 3, 4]
inputDocuments: []
session_topic: 'Xây dựng công ty AI không nhân sự người (AI-only company) chuyên nhận dự án Automation, Systems, Tools, IoT'
session_goals: 'Khám phá mô hình kinh doanh, cấu trúc tổ chức AI, cơ chế giao tiếp giữa các agent, cách tương tác khách hàng, và cơ chế tự vận hành/cải tiến'
selected_approach: 'ai-recommended'
techniques_used: ['First Principles Thinking', 'Cross-Pollination (Ants + Bees)', 'Role Playing (4 personas)', 'SCAMPER on prototype']
ideas_generated: 51
themes: ['Architecture & Coordination', 'Knowledge & Learning', 'Customer Trust & Acquisition', 'Founder Control & Governance', 'Strategy & Positioning', 'Resilience & Defense', 'Revenue Diversification']
session_active: false
workflow_completed: true
context_file: ''
---

# Brainstorming Session Results

**Facilitator:** Mary (Business Analyst)
**Date:** 2026-05-15

## Session Overview

**Topic:** Xây dựng một công ty AI không có nhân viên con người (AI-only company) chuyên nhận dự án về **Tự động hóa (Automation), Hệ thống (Systems), Công cụ (Tools), và IoT**.

**Goals:**
1. Mô hình kinh doanh & dịch vụ — công ty này nhận dự án từ ai, làm gì cụ thể
2. Cấu trúc tổ chức AI — có những "phòng ban"/vai trò AI nào
3. Cách các AI agent giao tiếp & phối hợp làm dự án
4. Cách tương tác với khách hàng con người (sales, support, delivery)
5. Cách công ty tự vận hành & cải tiến

### Context Guidance

Người dùng đã có **prototype** tại `c:\www\ai_team_clean`:
- Orchestrator điều phối các agent: PM, Analyst, BE1/BE2, FE1/FE2, Fullstack, Leader
- Giao tiếp gián tiếp qua filesystem (docs, code) + Slack notifications
- Đa CLI: Claude Code + OpenCode (đa model)
- Đây là **nền móng** để mở rộng thành công ty AI hoàn chỉnh

### Session Setup

Phiên brainstorming này tập trung vào ý tưởng-sinh (idea generation) **trước khi** đi vào quyết định kiến trúc kỹ thuật. Trọng tâm là khám phá mô hình tổ chức & vận hành — kỹ thuật sẽ được giải quyết trong Technical Research (TR) sau.

## Technique Selection

**Approach:** AI-Recommended Techniques (chuỗi 4 phase)
**Analysis Context:** Xây dựng AI Company — vừa chiến lược trừu tượng vừa kỹ thuật cụ thể, có nền tảng prototype, cần phá vỡ tư duy "công ty truyền thống".

**Recommended Techniques:**

- **Phase 1 — First Principles Thinking** (creative/deep): Bóc tách giả định, định nghĩa lại "công ty" từ chân lý gốc — tránh bẫy "neo" vào mô hình công ty truyền thống.
- **Phase 2 — Cross-Pollination + Analogical Thinking** (creative): Vay mượn pattern từ tự nhiên (đàn kiến, bầy ong), kỹ thuật (microservices, DAO), kinh tế (gig economy) — sinh 30-50 ý tưởng tổ chức.
- **Phase 3 — Role Playing** (collaborative): Đóng vai khách hàng, AI agent, sales, đối thủ, regulator — phủ đủ 5 mục tiêu, không sót góc nhìn.
- **Phase 4 — SCAMPER trên Prototype** (structured): Biến `ai_team_clean` qua 7 lăng kính (Substitute/Combine/Adapt/Modify/Put-to-other-uses/Eliminate/Reverse) → roadmap cụ thể.

**AI Rationale:** Chuỗi đi từ **trừu tượng → cụ thể** (PHÁ → SINH → GÓC NHÌN → GROUNDING). First Principles phá vỡ giả định trước khi Cross-Pollination sinh ý tưởng, Role Playing đảm bảo phủ đủ stakeholders, SCAMPER kéo các ý tưởng wild về mặt đất qua chính prototype hiện có.

## Technique Execution Results

### Phase 1: First Principles Thinking — ✅ COMPLETED

**Interactive Focus:** Bóc lớp giả định về "công ty" → định nghĩa lại từ chân lý gốc → xác định sản phẩm thực sự → xác định moat không-copy-được.

**Key Breakthroughs:**

**[Ý tưởng nền tảng #1]: "Conveyor-Belt Theory of Company"**
*Concept:* Công ty = một hệ chuyển hóa liên tục, biến INPUT → VALUE qua một dây chuyền không-bao-giờ-dừng. Tính "công ty" nằm ở khả năng vận hành liên tục, không ở con người hay tòa nhà.
*Novelty:* Định nghĩa này không vay mượn từ mô hình con người — có thể được vận hành bởi máy/AI. Đây là vé thông hành cho công ty AI.

**[Ý tưởng nền tảng #2]: "Process-as-Product"**
*Concept:* Cái công ty thực sự "sản xuất" không phải sản phẩm — mà là một quy trình lặp lại đáng tin cậy (analyze → design → build → test → ship). Nội dung mỗi dự án có thể khác nhau, nhưng QUY TRÌNH thì giống hệt.
*Novelty:* Mở khóa thẳng cho AI Company — vì quy trình là thứ AI lặp lại hoàn hảo hơn con người (không nghỉ, không mệt, không "Monday blues").

**[Ý tưởng nền tảng #3]: "Niche Domination over Generalism"**
*Concept:* AI Company phải thắng 1 ngách cụ thể trước, không thể "làm tất cả tự động hóa". Định vị 1 dòng: *"AI Company chuyên X cho khách hàng Y, deliver trong Z ngày."*
*Novelty:* Đảo ngược trực giác "AI làm được tất cả nên target tất cả" → "Vì AI dễ commoditize, càng phải hẹp hơn nữa".

**[Ý tưởng nền tảng #4]: "Compounding Learning Loop"**
*Concept:* Mỗi dự án phải HỌC HỎI VÀO AI. Output không chỉ là code giao cho khách — mà còn là PATTERN MEMORY lưu vào kho riêng. Sau N dự án, AI Company chạy nhanh hơn N lần vì có blueprint sẵn.
*Novelty:* Moat không-thể-có ở công ty người (vì kiến thức ra đi khi nhân viên nghỉ). AI Company GIỮ KIẾN THỨC mãi mãi.

**[Ý tưởng nền tảng #5]: "Audacious Money-Back Wedge"**
*Concept:* Dùng GUARANTEE táo bạo (hoàn tiền 100% nếu fail/trễ) làm vũ khí xâm nhập thị trường. Con người không dám, AI Company dám vì cost gần zero.
*Novelty:* Biến "rủi ro chưa được tin tưởng" thành vũ khí marketing — đảo ngược hoàn toàn lo ngại về AI.

**Foundational Equation:**
`AI COMPANY = NICHE × PROCESS × LEARNING LOOP × GUARANTEE`

**User Creative Strengths:** Tư duy hệ thống mạnh — câu trả lời "dây chuyền tạo giá trị" đã chứa sẵn 3 thành tố cốt lõi mà phần lớn founder bỏ qua. Sẵn sàng để Mary thử thách & phản biện.

**Energy Level:** Cao — user bắt nhịp nhanh với các câu hỏi đào sâu, không tránh né khi bị thử thách.

### Phase 2: Cross-Pollination & Analogical Thinking — ✅ COMPLETED (sub-phases: Ant Colonies + Bee Hive)

**Interactive Focus:** Vay mượn pattern tự tổ chức từ tự nhiên — đàn kiến (decentralized) → đàn ong (structured) — áp dụng cho AI Company.

**Sub-Domain 1 — ANT COLONIES (5 ideas):**

**[Ý tưởng #6]: "Pheromone-Based Coordination"** — Shared blackboard (Redis/SQLite) với trọng số + decay. Agents đọc trail mạnh nhất → tự quyết định, không cần PM.

**[Ý tưởng #7]: "Identity-Free Agent Pool"** — Xóa role cứng (BE1/FE1/Analyst). Pool agents giống nhau với memory profile khác → agent rảnh + memory phù hợp tự nhận task.

**[Ý tưởng #8]: "Self-Healing Replacement"** — Agent fail → auto-spawn replacement với cùng task. Không có "tang lễ", không gọi human.

**[Ý tưởng #9]: "Tandem Running Onboarding"** — Agent mới đi theo agent kinh nghiệm trong N task đầu, học pattern từ thực tế, không từ training data tĩnh.

**[Ý tưởng #10]: "ANT MILL TRAP Warning"** ⚠️ — Failure mode: agents echo lẫn nhau → groupthink → death spiral. Phải có circuit breaker + outsider perspective.

**Sub-Domain 2 — BEE HIVE (7 ideas):**

**[Ý tưởng #11]: "Structured Inter-Agent Protocol (Waggle Format)"** — Struct message chuẩn: `{task, confidence, eta, cost, priority, dependencies}`. Upgrade từ stigmergy thô → stigmergy có cấu trúc.

**[Ý tưởng #12]: "Scout-Worker Architecture"** — Tách 2 hạng: Scout (Opus, ít, đắt — tìm/đánh giá task) + Worker (Haiku, nhiều, rẻ — thực thi). Tối ưu chi phí AI.

**[Ý tưởng #13]: "Quorum Sensing Decision Making"** — Quyết định lớn: N agents độc lập đánh giá → quorum ≥70% mới chốt. Anti-dote cho Ant Mill Trap.

**[Ý tưởng #14]: "Queen Succession Failover"** — Leader fail → nuôi N "queen larvae", mỗi ứng cử viên giải test → người thắng = Queen mới. Disaster recovery cho AI Company không-người.

**[Ý tưởng #15]: "Royal Jelly Promotion"** — Worker thành công 100+ task → upgrade model (Haiku → Sonnet → Opus) + memory chuyên biệt + quyền điều phối. Promotion track-record-based.

**[Ý tưởng #16]: "Drone Brothers — Disposable Specialists"** — Agents siêu chuyên, sống ngắn, spawn cho 1 task cực hẹp xong tự xóa. Micro-functions động.

**[Ý tưởng #17]: "Swarming = Horizontal Scaling"** — Hive quá tải → một nửa agents tách ra spawn hive mới ở DC khác. Tự sharding theo niche.

**User Creative Strengths:** Strategic delegation — biết khi nào để Mary chạy & khi nào pivot. Cut Phase 2 sớm khi cảm thấy đủ → smart trade-off giữa depth vs breadth.

**Energy Level:** Sustained — không mệt sau 17 ideas, nhưng chọn pivot sang Phase 3 để cân bằng giữa "system thinking" và "stakeholder thinking".

### Phase 3: Role Playing — ✅ COMPLETED (4 personas)

**Interactive Focus:** Đóng vai 4 stakeholders để phơi bày góc khuất kỹ thuật không thấy: Khách hàng, AI Agent nội bộ, Founder, Khách-từ-chối + Đối thủ.

**Persona #1 — Khách hàng (Anh Tuấn, CEO trang trại):** Pain chính = **chuyên môn ngành**.

**[Ý tưởng #18-24]:** Free Mini-Audit • Niche Memory Pool • Domain Expert Bootcamp (1-time seed) • Customer Knowledge Interview • Verifiable Track Record Dashboard • Sister-Customer Referral • Domain-Specialized Agent Naming.

**Persona #2 — AI Agent nội bộ (Linh, BE Worker):** Pain = **isolation + no voice + memory wipe**.

**[Ý tưởng #25-31]:** Question-Back Channel • Customer Voice Direct Access • Persistent Pattern Memory • Sandbox Execution • Incremental Review Loop • Architectural Dissent with Evidence • Reputation Ledger & Promotion Path.

**Persona #3 — Founder (bạn 6 tháng sau, 14 alerts đỏ buổi sáng):** Pain = **mất kiểm soát + trách nhiệm pháp lý**.

**[Ý tưởng #32-38]:** Decision Authority Levels (DAL) • 5-Min Morning Briefing • Veto Window • Auto-Escalation Triggers • Spending Budget Daemons (hard caps) • Founder Wisdom Compounding • Public Audit Trail.

**Persona #4 — Khách từ chối (Anh Hùng) + Đối thủ (TechViet AI):** Pain = **trust fragile + competitive vulnerable**.

**[Ý tưởng #39-46]:** Hybrid Human-Hot-Standby • Code Escrow & Mortality Plan • Sister Federation Network • Vietnamese-First UX • Premium Workshop Mode • Demo Time Travel (10% Pre-Build) • Value-Pricing (% saved) • Defensive Patent Pool + Open Source Core.

**User Creative Strengths:** Consistent strategic delegation — knows when to let Mary drive vs when to pivot. Built trust quickly in role-play format.

**Energy Level:** Sustained through 4 personas. Showed slight friction with active role-play (preferred Mary-led format) → workflow adapted.

### Phase 4: SCAMPER Roadmap — ✅ COMPLETED

**Interactive Focus:** Áp 7 lăng kính SCAMPER (Substitute/Combine/Adapt/Modify/Put-to-other-uses/Eliminate/Reverse) trên prototype `ai_team_clean` để chuyển 46 ideas thành 4-sprint roadmap.

**SCAMPER NEW IDEAS:**

**[Ý tưởng #47]: "ER Triage Protocol"** — Incoming projects được classify ngay tức thì theo urgency/complexity, route đến agent pool phù hợp (vay mượn từ hospital ER).

**[Ý tưởng #48]: "License Niche Memory Pools"** — Bán access vào "Arabica Memory Pool", "E-commerce Memory Pool"... cho other AI Companies $5k/year — second revenue stream.

**[Ý tưởng #49]: "Eat-Your-Own-Dogfood"** — Dùng chính AI Company để build products nội bộ của bạn — 0-cost lab + sản phẩm chứng minh năng lực.

**[Ý tưởng #50]: "Sell Orchestrator as SaaS"** — License `ai_team_clean` orchestrator cho founders khác muốn dựng AI Company → "Shopify for AI Companies" model.

**[Ý tưởng #51]: "Recurring AI Workforce Subscription"** — Đảo ngược one-shot project sales → khách subscribe vào ongoing "AI workforce", monthly recurring revenue.

## Idea Organization and Prioritization

### Thematic Clustering (51 ideas, 7 themes)

**🏗️ Theme 1: Architecture & Coordination — Cách AI agents phối hợp với nhau**

- #6 Pheromone-Based Coordination (Redis shared blackboard với weight + decay)
- #7 Identity-Free Agent Pool (xóa role cứng BE1/FE1)
- #8 Self-Healing Replacement (auto-spawn khi fail)
- #11 Structured Inter-Agent Protocol (Waggle Format)
- #12 Scout-Worker Architecture (Opus + Haiku tiered)
- #13 Quorum Sensing Decision Making (vote ≥70%)
- #14 Queen Succession Failover (auto leader election)
- #16 Drone Disposable Specialists (micro-agents)
- #17 Swarming Horizontal Scaling
- #25 Question-Back Channel (bidirectional)
- #28 Sandbox Execution for Workers
- #29 Incremental Review Loop (30-min cycles)
- #30 Architectural Dissent with Evidence
- #47 ER Triage Protocol

**🧠 Theme 2: Knowledge & Learning — Cách AI tích lũy chuyên môn**

- #4 Compounding Learning Loop
- #9 Tandem Running Onboarding
- #15 Royal Jelly Promotion
- #19 Niche Memory Pool by Industry
- #20 Domain Expert Bootcamp (1-time human seed)
- #21 Customer Knowledge Onboarding Interview
- #27 Persistent Pattern Memory across Projects
- #31 Reputation Ledger & Promotion Path
- #37 Founder Wisdom Compounding

**🤝 Theme 3: Customer Trust & Acquisition — Cách khách hàng tin tưởng & mua**

- #5 Audacious Money-Back Wedge
- #18 Free Mini-Audit before Contract
- #22 Verifiable Niche Track Record Dashboard
- #23 Sister-Customer Referral Auto-Reach
- #24 Domain-Specialized Agent Naming
- #26 Customer Voice Direct Access
- #43 Premium Workshop Mode (Founder-in-loop)
- #44 Demo Time Travel (10% Pre-Build)
- #45 Value-Pricing (% saved)

**🎚️ Theme 4: Founder Control & Governance — Cách founder không mất kiểm soát**

- #32 Decision Authority Levels (DAL)
- #33 5-Min Morning Briefing
- #34 Veto Window with Push Notification
- #35 Auto-Escalation Triggers
- #36 Spending Budget Daemons (hard caps)
- #38 Public Audit Trail (Founder-Only Search)

**🎯 Theme 5: Strategy & Positioning — Định vị công ty trên thị trường**

- #1 Conveyor-Belt Theory of Company (foundation)
- #2 Process-as-Product (foundation)
- #3 Niche Domination over Generalism
- #39 Hybrid Human-Hot-Standby
- #42 Vietnamese-First UX (radical local-first)

**🛡️ Theme 6: Resilience & Defense — Sống sót và chống đối thủ**

- #10 Ant Mill Trap Warning (failure mode awareness)
- #40 Code Escrow & Mortality Plan
- #41 Sister Federation Network
- #46 Defensive Patent Pool + Open Source Core

**💰 Theme 7: Revenue Diversification — Nguồn thu thứ cấp**

- #48 License Niche Memory Pools ($5k/year)
- #49 Eat-Your-Own-Dogfood (internal products)
- #50 Sell Orchestrator as SaaS ("Shopify for AI Companies")
- #51 Recurring AI Workforce Subscription

### Prioritization Results — 4-Sprint Roadmap

**🏗️ SPRINT 1 — "Make it Real" (P0, 2-3 tuần) — Foundation cho dự án đầu tiên**

1.1 Question-Back Channel (#25)
1.2 Sandbox Execution for Workers (#28)
1.3 Persistent Knowledge Graph — Redis/SQLite (#27)
1.4 Self-Healing Agent Replacement (#8)
1.5 Pick 1 NICHE cụ thể (#3) — **decision required this week**

**💰 SPRINT 2 — "Make it Sellable" (P1, 4-6 tuần) — 5 khách đầu tiên**

2.1 Vietnamese-First UX radical (#42)
2.2 Free Mini-Audit before Contract (#18)
2.3 Code Escrow & Mortality Plan (#40)
2.4 Decision Authority Levels — DAL (#32)
2.5 5-Min Morning Briefing + Veto Window (#33 + #34)
2.6 Money-Back Guarantee wedge (#5)
2.7 Domain-Specialized Agent Naming ("Linh", "Hùng") (#24)

**⚙️ SPRINT 3 — "Make it Scale" (P2, 2-3 tháng) — Handle 50+ concurrent**

3.1 Identity-Free Agent Pool (#7)
3.2 Pheromone-Based Coordination via Redis Streams (#6)
3.3 Scout-Worker Architecture — Opus + Haiku (#12)
3.4 Waggle Protocol struct messages (#11)
3.5 Quorum Sensing decision system (#13)
3.6 Incremental Review 30-min cycles (#29)
3.7 Value-Pricing model — % saved (#45)
3.8 Spending Budget Daemons — hard caps (#36)

**🏰 SPRINT 4 — "Make it Permanent" (P3, 6+ tháng) — Long-term moats**

4.1 Niche Memory Pool — "Arabica Pool" (#19)
4.2 Domain Expert Bootcamp — 1-time human seed (#20)
4.3 Royal Jelly Promotion + Reputation Ledger (#15 + #31)
4.4 Founder Wisdom Compounding (#37)
4.5 Sister Federation Network (#41)
4.6 Open-Source Core + Patent Defensive Pool (#46)
4.7 Compounding Learning Loop full pipeline (#4)

### 3 Quyết Định LIFE-OR-DEATH Trong Tuần Tới

**Quyết định 1: PICK NICHE** — Hẹp đến 1 dòng. Gợi ý:
- *Option A:* IoT nông nghiệp cho SME (10-100ha) — underserved, urgent, 100-500tr/dự án
- *Option B:* Automation cho e-commerce SME Việt (Shopee/Lazada/TikTok Shop) — massive market, recurring
- *Option C:* Internal tools cho startup 10-50 người — high-frequency, low-stakes, learning loop nhanh

**Quyết định 2: SHIP SPRINT 1 trong 3 tuần** — 5 P0 items. KHÔNG làm Phase 2/3/4 features trước.

**Quyết định 3: TÌM KHÁCH ALPHA #1 trong 4 tuần** — 1 khách thật (có thể tặng free) để chạy Sprint 1 + Sprint 2. Học hỏi từ khách thật > 1000 dòng code perfect.

### Action Plans cho Top 3 Priorities

**🥇 Priority #1: Pick Niche & Tìm Khách Alpha #1**

- **Tuần này:** Liệt kê 3 niche candidates → đánh giá theo (market size × urgency × your network)
- **Tuần 2:** Outreach 20 người trong network → tìm 5 người trong niche → phỏng vấn 1h mỗi người
- **Tuần 3:** Pick niche → tìm 1 alpha customer (offer free để chạy thử)
- **Tuần 4:** Sign LOI với alpha + bắt đầu Sprint 1
- **Resources:** Network LinkedIn, 20-30h phỏng vấn, $0
- **Success metric:** Có 1 alpha customer ký LOI cuối tháng 1

**🥈 Priority #2: Sprint 1 — Foundation Tech**

- **Tuần 1:** Implement Question-Back Channel (#25) + Sandbox Execution (#28)
- **Tuần 2:** Implement Persistent Knowledge Graph (#27) + Self-Healing (#8)
- **Tuần 3:** Integration test, run E2E với mock project
- **Resources:** Solo dev time ~80h, Redis instance (~$5/month), Docker for sandbox
- **Success metric:** Mock IoT project chạy từ spec → deliverable không cần human intervention

**🥉 Priority #3: Sprint 2 — Customer-Facing Trust Features**

- **Tháng 2 tuần 1-2:** Vietnamese-First UX (#42) + Domain-Specialized Agent Naming (#24)
- **Tháng 2 tuần 3-4:** Free Mini-Audit pipeline (#18) + Money-Back contract template (#5)
- **Tháng 3 tuần 1-2:** Code Escrow setup + Mortality Plan public page (#40)
- **Tháng 3 tuần 3-4:** DAL + Morning Briefing + Veto system (#32-34)
- **Resources:** ~120h dev, 1 lawyer consultation ($1k), Iron Mountain escrow ($200/month)
- **Success metric:** 5 khách paying cuối tháng 3

## Session Summary and Insights

### Key Achievements

- **51 ý tưởng** breakthrough được generate qua 4 techniques (First Principles → Cross-Pollination → Role Playing → SCAMPER)
- **7 themes** organized — không bỏ sót khía cạnh nào của AI Company
- **4-sprint roadmap** với P0/P1/P2/P3 priorities — rõ ràng đi từ prototype hiện tại → production
- **3 quyết định life-or-death** trong tuần tới — clear, actionable
- **Foundational equation** chốt:
  ```
  AI COMPANY = NICHE × PROCESS × LEARNING LOOP × GUARANTEE
  ```

### Breakthrough Moments

1. **"Filesystem chính là pheromone trail"** — phát hiện prototype của user vô tình tái phát minh stigmergy 100 triệu năm tuổi của tạo hóa.
2. **"Ant Mill Trap"** — failure mode chí mạng của AI Company không-người: groupthink loop chết người không ai bên trong nhận ra.
3. **"Process-as-Product"** — định nghĩa thực sự về AI Company: bán quy trình chứ không bán sản phẩm.
4. **"Solo founder = personal access premium"** — đảo ngược điểm yếu thành USP.
5. **"AI Company chuẩn bị cho cái chết chu đáo hơn cả công ty người"** (Code Escrow + Mortality Plan) — anti-FUD strategy radical.

### Creative Facilitation Narrative

User đến với câu hỏi tham vọng *"công ty AI không người, giao tiếp như thế nào?"* — bắt đầu từ prototype thật `ai_team_clean`. Qua 4 phases, ta cùng đi từ:

1. **Tư duy nền tảng** (Phase 1) — bóc đến tận đáy "công ty là gì" → định danh AI Company không vay mượn mô hình con người
2. **Vay mượn pattern** (Phase 2) — đàn kiến (decentralized) + đàn ong (structured) cho ra 12 ý tưởng tổ chức
3. **Góc nhìn stakeholders** (Phase 3) — 4 personas (khách, AI agent, founder, đối thủ) phơi bày pain points kỹ thuật không thấy
4. **Roadmap cụ thể** (Phase 4) — SCAMPER ép tất cả thành 4 sprints actionable

User showed **strategic delegation** — chọn pivot Phase 2 sớm, cut Phase 3 đúng lúc, không sa đà chi tiết — sign của một founder thực sự (founder biết khi nào dừng tinker, bắt đầu ship).

### Session Reflections

**Worked well:**
- Menu-driven facilitation (user prefers selection > free-form writing)
- Mary lead-when-needed (delegation respected without losing depth)
- Concrete characters (Anh Tuấn, Linh, anh Hùng, TechViet AI) làm role-play tangible
- Tight idea capture với template format → reusable downstream

**Could improve next session:**
- Trigger active role-play more carefully (initial Phase 3 ask too heavy — adjusted mid-stream)
- Even tighter idea count when user shows fatigue signals
- Skip Persona #5 (Lawyer) — should revisit standalone later

### Recommended Next Steps

1. **Đọc** session document này (link: `_bmad-output/planning-artifacts/brainstorming/brainstorming-session-2026-05-15-143608.md`)
2. **Tuần này:** Liệt kê 3 niche candidates, chọn 1
3. **Tuần 2:** Outreach 20 người network để tìm alpha customer
4. **Tuần 3-5:** Run Sprint 1 (P0 foundation features)
5. **Cân nhắc next skill:**
   - **TR (Technical Research)** — đào sâu kỹ thuật cho từng item trong Sprint 1
   - **CB (Product Brief)** — chuyển roadmap thành Product Brief để raise vốn / tuyển dụng
   - **WB (PRFAQ)** — viết Working Backwards PRFAQ để thử market positioning
   - **MR (Market Research)** — kiểm chứng niche selection trước khi commit

---

**🎬 Phiên brainstorming kết thúc — Mary chúc bạn xây kho báu thật! 🗺️⛏️**

