# Frontend Gesture + Scanner Test Plan

Este plano cobre os testes funcionais pendentes para:
- `HandGestureController` (7.4)
- `NeonRenderer` (8.3)
- integração gesto + grafo (10.4)
- UI de configuração de scanner (12.3)

## 1) HandGestureController (7.4)

1. **Permissão webcam**
   - Bloquear permissão no navegador.
   - Esperado: mensagem `Permissao de webcam necessaria`.
2. **Sem webcam**
   - Iniciar em VM sem câmera.
   - Esperado: `Webcam nao encontrada`.
3. **Conexão WebSocket**
   - Com backend rodando, ativar controle.
   - Esperado: status `Ativo` + FPS > 0.
4. **Ativar/Desativar**
   - Alternar botão `Ativar/Desativar Controle por Gestos`.
   - Esperado: stream inicia/para e cursor virtual some ao desativar.

## 2) NeonRenderer (8.3)

1. **Render landmarks**
   - Com mãos detectadas, validar pontos neon nos dedos.
2. **Color cycling**
   - Observar transição cíclica ciano/magenta/azul (~3s).
3. **Trails**
   - Mover mão rapidamente e validar trilha com fade.
4. **Performance degrade**
   - Forçar CPU alta.
   - Esperado: ativar `tracking-only` e manter responsividade.

## 3) Graph Gesture Integration (10.4)

1. **Seleção por pinch**
   - Pinch sobre nó.
   - Esperado: nó selecionado e destacado.
2. **Drag por pinch contínuo**
   - Manter pinch e mover mão.
   - Esperado: nó acompanha movimento.
3. **Zoom**
   - `v_sign` => zoom in, `closing_v` => zoom out.
4. **Compatibilidade mouse**
   - Usar mouse depois de gestos.
   - Esperado: interação normal sem conflito.

## 4) Scanner UI Config (12.3)

1. **Troca Local/GitHub**
   - Alternar modo e validar campos dinâmicos.
2. **Validação de formulário**
   - Enviar repo inválido (`owner`).
   - Esperado: erro de validação.
3. **Persistência localStorage**
   - Atualizar configurações e recarregar página.
   - Esperado: valores persistidos.
4. **Progresso**
   - Iniciar scan e validar barra/contadores/erros/cancelamento.

## Evidências

Registrar capturas em:
- `docs/screenshots/gesture-controller/`
- `docs/screenshots/neon-renderer/`
- `docs/screenshots/scanner-config/`
