#Requires -Version 5.1
# Migration 0.4.81 -> 0.4.82
#
# bug-119 - ceifa automatica de CLI de agente orfao.
#
# O runtime passa a registrar em SQLite (tabela agent_processes, criada sozinha
# pelo create_all na primeira abertura do banco) a identidade de cada CLI que
# lanca: pid, nome da imagem, instante de criacao lido do sistema operacional e
# pid do runtime dono. Os polls que ja existiam (status, list, watch, create)
# ceifam o que sobrou. Nenhum daemon, processo novo ou thread de poll.
#
# policies.json ganha "orphan_agent_reap_after_s": 120 pelo merge aditivo do
# template. Valor negativo desliga a ceifa.
param()
Write-Host '[OK] Migration 0.4.81-to-0.4.82 applied.'
