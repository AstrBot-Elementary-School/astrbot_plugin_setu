# 项目文档

这里介绍插件的功能、设计取舍和当前实现。

## 目录

- [`overview.md`](./overview.md): 项目定位、能力边界、核心特性
- [`architecture.md`](./architecture.md): 分层、启动流程、调用链和数据归属
- [`sending-limits.md`](./sending-limits.md): OneBot/NapCat 传输实测与排查

## 职责边界

- `overview.md` 解释"为什么是这个插件形态"，不承载细节规则。
- `architecture.md` 解释"模块如何连接"，不复制各模块算法。

## 适合谁看

- 第一次接手这个插件的维护者
- 需要了解当前实现边界的协作者
- 准备规划新功能或排查架构问题的人

## 推荐阅读顺序

1. [`overview.md`](./overview.md)
2. [`architecture.md`](./architecture.md)
