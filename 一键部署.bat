@echo off
chcp 65001 >nul
title 智能数据分析助手
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy.ps1"