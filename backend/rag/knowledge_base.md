id: defect_type_crack
title: 裂纹缺陷说明
category: defect_type
tags: 裂纹,critical,边部,头部
defect_types: 裂纹
risk_level: critical
applicable_intents: explain,root_cause,review,uncertain_cause,spatial
evidence_type: defect_explanation
related_doc_ids: severity_rule,defect_cause_checklist,review_loop_standard,spatial_distribution_rule,response_style_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
裂纹通常属于高风险缺陷。若裂纹集中在方坯头部或边部，应优先检查切头状态、拉速波动、冷却均匀性、结晶器液面波动和表面应力集中。

id: defect_type_scar
title: 结疤缺陷说明
category: defect_type
tags: 结疤,major,表面
defect_types: 结疤
risk_level: major
applicable_intents: explain,root_cause,review
evidence_type: defect_explanation
related_doc_ids: defect_cause_checklist,review_loop_standard,severity_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
结疤常表现为局部片状或块状异常区域。若在同一炉号或同一表面连续出现，建议检查坯壳形成、保护渣状态和辊道接触异常。

id: defect_type_scale
title: 氧化皮缺陷说明
category: defect_type
tags: 氧化皮,minor,底面
defect_types: 氧化皮
risk_level: minor
applicable_intents: explain,false_positive,review,root_cause
evidence_type: defect_explanation
related_doc_ids: review_loop_standard,response_style_rule,severity_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
氧化皮类缺陷可能与表面氧化、除鳞效果、照明反光和检测阈值有关。需要结合人工复核区分真实表面缺陷和视觉误检。

id: severity_rule
title: 缺陷等级规则
category: severity
tags: severity,critical,major,minor,等级
defect_types: 裂纹,结疤,夹渣,凹坑,划伤,麻点,压痕,氧化皮
risk_level: mixed
applicable_intents: severity,standard,review,explain
evidence_type: severity_rule
related_doc_ids: defect_type_crack,review_loop_standard,response_style_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
第一阶段 MVP 可将裂纹归为 critical，将结疤、夹渣、凹坑归为 major，将划伤、麻点、压痕、氧化皮归为 minor。实际投产时应以现场质检标准和客户判定规则为准。

id: billet_surface_standard
title: 方坯表面缺陷判定标准
category: standard
tags: 判定标准,方坯,表面
defect_types: all
risk_level: mixed
applicable_intents: standard,spatial,review,quality
evidence_type: surface_standard
related_doc_ids: spatial_distribution_rule,review_loop_standard,response_style_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
方坯表面缺陷分析应同时关注缺陷类别、严重等级、所在表面、长度方向位置、宽度方向位置、炉号、计划号和方坯 ID。质量异常结论必须引用可追溯数据，不应只凭单条检测结果判断整炉异常。

id: report_template
title: 缺陷分析报告模板
category: report_template
tags: 报告,模板,统计,空间分布
defect_types: all
risk_level: mixed
applicable_intents: report,quality,spatial
evidence_type: report_template
related_doc_ids: billet_surface_standard,spatial_distribution_rule,response_style_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
报告建议包含：数据范围、样本口径、缺陷类别分布、表面分布、头中尾位置分布、边部/中心分布、炉号/计划号/方坯 NG 率排名、典型原图证据、质量风险判断和复核建议。

id: defect_type_scratch
title: 划伤缺陷说明
category: defect_type
tags: 划伤,minor,辊道,接触
defect_types: 划伤
risk_level: minor
applicable_intents: explain,root_cause,review
evidence_type: defect_explanation
related_doc_ids: defect_cause_checklist,review_loop_standard,severity_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
划伤通常表现为细长线状或条带状表面异常，常与导卫、辊道、夹送辊或运输过程中的机械接触有关。若划伤沿长度方向连续出现，应关注接触部件磨损、异物压入和在线输送稳定性。

id: defect_type_pit
title: 凹坑缺陷说明
category: defect_type
tags: 凹坑,major,表面,冷却
defect_types: 凹坑
risk_level: major
applicable_intents: explain,root_cause,review,spatial
evidence_type: defect_explanation
related_doc_ids: defect_cause_checklist,review_loop_standard,severity_rule,spatial_distribution_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
凹坑常表现为局部下陷或暗斑区域，可能与坯壳局部缺陷、冷却不均、表面氧化剥落或检测角度造成的阴影有关。若凹坑集中在边部或同一表面，应结合原图、深度感知和人工复判确认。

id: defect_type_slag
title: 夹渣缺陷说明
category: defect_type
tags: 夹渣,major,冶炼,保护渣
defect_types: 夹渣
risk_level: major
applicable_intents: explain,root_cause,review,quality
evidence_type: defect_explanation
related_doc_ids: defect_cause_checklist,review_loop_standard,severity_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
夹渣类缺陷与钢水洁净度、保护渣卷入、结晶器液面波动和二冷段状态有关。若夹渣在同一炉号或同一计划号内高频出现，应优先复核冶炼与连铸工艺记录，不能只凭单张图像直接下结论。

id: defect_type_hemp_spot
title: 麻点缺陷说明
category: defect_type
tags: 麻点,minor,表面,阈值
defect_types: 麻点
risk_level: minor
applicable_intents: explain,false_positive,review,root_cause
evidence_type: defect_explanation
related_doc_ids: review_loop_standard,response_style_rule,severity_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
麻点通常表现为小面积离散点状异常，可能来自轻微表面粗糙、氧化点、照明噪声或算法阈值偏低。分析时应关注数量、分布密度、置信度和是否跨相机重复出现。

id: defect_type_indent
title: 压痕缺陷说明
category: defect_type
tags: 压痕,minor,major,机械接触
defect_types: 压痕
risk_level: minor,major
applicable_intents: explain,root_cause,review
evidence_type: defect_explanation
related_doc_ids: defect_cause_checklist,review_loop_standard,severity_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
压痕常表现为局部规则形变或边界较清晰的受压区域，可能与辊道接触、夹持设备、运输碰撞或局部异物压入有关。若压痕集中于固定宽度位置，应检查对应机械接触点。

id: defect_cause_checklist
title: 常见缺陷原因排查清单
category: root_cause
tags: 原因,排查,工艺,复核
defect_types: all
risk_level: mixed
applicable_intents: root_cause,uncertain_cause,review,quality
evidence_type: root_cause_checklist
related_doc_ids: review_loop_standard,response_style_rule,spatial_distribution_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
缺陷原因分析应分层排查：先看检测证据是否充分，再看空间分布是否集中，最后关联炉号、计划号、方坯 ID 和工艺记录。裂纹重点关注拉速、冷却和应力集中；结疤与夹渣关注钢水洁净度、保护渣和坯壳形成；划伤、压痕关注导卫、辊道和运输接触；氧化皮、麻点关注表面氧化、除鳞、照明和阈值。

id: review_loop_standard
title: 缺陷复核闭环建议
category: review
tags: 复核,闭环,人工确认,质量风险
defect_types: all
risk_level: mixed
applicable_intents: review,quality,uncertain_cause,root_cause
evidence_type: review_loop
related_doc_ids: defect_cause_checklist,response_style_rule,billet_surface_standard
status: active
version: v0.3.2
updated_at: 2026-06-26
---
高置信度或 critical 缺陷应优先进入人工复核队列，并保留原图、bbox、相机、表面位置和时间戳。对于同一炉号、同一计划号或同一方坯连续出现的缺陷，应形成质量关注项；对于 pending 或疑似误检记录，应先复判再进入质量风险结论。

id: spatial_distribution_rule
title: 方坯空间分布解释规则
category: spatial_rule
tags: 头部,中部,尾部,边部,中心,空间分布
defect_types: all
risk_level: mixed
applicable_intents: spatial,root_cause,review,quality
evidence_type: spatial_rule
related_doc_ids: defect_cause_checklist,billet_surface_standard,response_style_rule
status: active
version: v0.3.2
updated_at: 2026-06-26
---
头部缺陷集中可能与切头、起拉阶段和头部温度状态有关；尾部集中可能与收尾阶段稳定性有关；边部集中通常需要关注应力集中、角部冷却和机械接触；中心区域集中则更需要结合表面状态、光照和检测阈值排查。空间分布只能作为复核线索，不能单独作为工艺事故判定依据。

id: response_style_rule
title: 缺陷知识解释回答规范
category: answer_rule
tags: 回答规范,知识解释,证据
defect_types: all
risk_level: mixed
applicable_intents: answer_style,uncertain_cause,root_cause,review
evidence_type: answer_rule
related_doc_ids: defect_cause_checklist,review_loop_standard
status: active
version: v0.3.2
updated_at: 2026-06-26
---
回答缺陷知识解释问题时，应区分“当前样本统计事实”和“知识库经验解释”。统计数字必须来自工具结果；原因和建议来自知识库时，应使用“可能”“建议复核”“优先检查”等审慎表述，并说明仍需结合人工复判和现场工艺记录。
