
## 资产管理

ModelArts安装或升级后，需要上传算子包、算子镜像、模型资产、模型镜像等各类资源，其中算子包和资产文件需要上传到OBS中，上传之前有些需要解压缩，有些不需要，镜像上传之前需要使用docker load镜像，配置swr登陆命令和组织名等，再完成上传。

因为资源文件很多（可能有上百个），如果手动操作耗时且容易出错，需要构建一个脚本来完成。

为了有更好的适配性，构建一个独立的python脚本，不需要其他依赖，直接复制到某个节点就可以使用。

### 前提条件

docker镜像上传依赖docker cli，环境上应配置好了docker，并通过swr的登陆命令完成登陆。

### 详细诉求

1. 支持资产清单校验，保证资产完整，由文本文件提供资产清单，检查当前目录下所需资产是否完整；
2. 通过本地配置文件配置OBS路径和ak/sk，通过任务文件配置资产列表和上传桶及路径，需要解压的资产需要指定解压策略；
3. 支持记录上传进度，断点续传，异常日志。

### 支持的资源类型

#### 数据工程算子

样例：
```
NLP_qa_cot_score-aarch64-1.3.1-xxxxxxxx.tar
NLP_qa_quality_score-aarch64-1.3.1-xxxxxxxx.tar
```

需要上传到dataengineering-model-{region_code}或dataengineering-model桶中，路径为/OPERATOR/SYS。

#### 镜像

样例：
```
hce-arm-python3.9-custom-operator-3.8.0.xxxxxxxx-aarch64.tar
hce-arm-python3.10-custom-operator-910c-3.8.0.xxxxxxxx-aarch64.tar
```

上传到盘古承载租户中，组织名为：com-huaweicloud-dataengineering。
