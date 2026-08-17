# 사용법

이 도구는 GitHub에서 작성한 외부 저장소의 Issue와 Pull Request를 찾아 `README.md`로 만듭니다. Python 표준 라이브러리와 GitHub GraphQL API만 사용하는 독립 구현입니다.

## 설정

GitHub 저장소의 **Settings → Secrets and variables → Actions → Variables**에서 필요한 값만 등록합니다. 아무 값도 등록하지 않으면 기본값으로 동작합니다.

| 변수 | 기본값 | 용도 |
| --- | --- | --- |
| `GITHUB_USERNAME` | `YangSiJun528` | 수집할 GitHub 사용자 |
| `TITLE` | `Open Source Contributions` | README 제목 |
| `MIN_STARS` | `100` | 저장소의 최소 현재 star 수 |
| `INCLUDE_REPOS` | 빈 값 | star 수와 관계없이 포함할 저장소 |
| `EXCLUDE_REPOS` | 빈 값 | 항상 제외할 저장소 |
| `SHOW_SELF_CLOSED_REPOS` | 빈 값 | 추적 사용자가 만들고 직접 닫은 항목도 표시할 저장소 |
| `INCORPORATED_PRS` | 빈 값 | `Adopted`로 표시할 PR |

여러 값은 쉼표로 구분합니다. 대소문자는 구분하지 않고 각 값의 앞뒤 공백은 제거합니다.

```text
INCLUDE_REPOS=owner1/repo1,owner2/repo2
EXCLUDE_REPOS=owner3/repo3
SHOW_SELF_CLOSED_REPOS=owner1/repo1
INCORPORATED_PRS=spring-projects/spring-framework#12345,owner/repo#456
```

저장소는 다음 순서로 필터링합니다.

1. 사용자가 소유한 저장소는 제외합니다.
2. `EXCLUDE_REPOS`에 있으면 제외합니다.
3. `INCLUDE_REPOS`에 있으면 포함합니다.
4. 나머지는 star 수가 `MIN_STARS` 이상일 때 포함합니다.
5. `GITHUB_USERNAME`이 생성했고 마지막 종료자도 같은 사용자인 Issue와 unmerged PR은 기본적으로 제외합니다.

`SHOW_SELF_CLOSED_REPOS`에 등록한 저장소는 5번 필터를 적용하지 않습니다. 이 설정은 `EXCLUDE_REPOS`나 star 조건을 무시하지 않으므로, star가 낮은 저장소라면 `INCLUDE_REPOS`에도 함께 등록해야 합니다. 생성자와 마지막 종료자가 모두 `GITHUB_USERNAME`과 일치할 때만 제외하며, 둘 중 하나라도 다르거나 GitHub에서 확인되지 않으면 표시합니다.

본인이 열고 직접 닫은 Issue라도 본인이 작성한 merged PR이 연결되어 있으면 표시합니다. GitHub의 closing-PR 연결 또는 Issue 본문과 본인 댓글에 있는 같은 저장소의 `#123`, `owner/repo#123`, PR URL을 확인하고, 해당 번호가 실제로 본인이 작성한 merged PR인지 API로 검증합니다. 본인이 닫은 unmerged PR은 숨기되 `INCORPORATED_PRS`에 등록한 PR은 `Adopted`로 표시합니다.

PR 상태는 명시적 override, GitHub의 merged 상태, open 상태, closed 상태 순서로 결정합니다. `INCORPORATED_PRS`에 등록한 PR은 `Adopted`로 표시하며, 그 외 closed/unmerged PR을 임의로 수락 또는 거절로 해석하지 않습니다.

## 실행

**Actions → Update Open Source Contributions → Run workflow**에서 수동 실행할 수 있습니다. 자동 실행은 `0 15 * * *`이며, 매일 KST 00:00에 예약됩니다. GitHub의 queue 상황에 따라 실제 시작은 늦어질 수 있습니다.

workflow는 저장소 기본 `GITHUB_TOKEN`과 `contents: write` 권한만 사용합니다. 별도 PAT는 필요하지 않습니다. 생성 결과가 기존 `README.md`와 같으면 커밋하지 않으며, 변경된 경우 `github-actions[bot]`이 커밋합니다.

## 미리보기 사용

workflow는 최근 5개 기여를 담은 `preview-5.svg`도 함께 갱신합니다. 다른 README에서 아래처럼 사용하면 이미지 전체가 이 저장소로 연결됩니다.

```markdown
[![Open-Source Contributions](https://raw.githubusercontent.com/YangSiJun528/my-oss-contributions/main/preview-5.svg)](https://github.com/YangSiJun528/my-oss-contributions)
```

미리보기에는 제목, 기여 5개, 전체 내역 링크만 표시합니다. 원격 README에 위 코드를 직접 추가하지는 않습니다.

## 템플릿

문서 형식은 `README.template.md`에서 수정합니다. 다음 placeholder는 반드시 유지해야 합니다.

```text
{{TITLE}}
{{CONTRIBUTIONS}}
```

기여 목록은 날짜, 유형, 상태, 저장소, 제목 순서의 한 줄 레코드입니다. 저장소 열은 27칸이며 더 길면 owner를 생략합니다. 제목은 표시 폭 81칸 이상일 때 줄여 `...`을 붙이고, 최종 폭은 최대 84칸입니다. ASCII 영문과 숫자는 1칸, 한글·한자·전각 문자와 이모지는 2칸으로 계산합니다. 축약해도 링크와 hover에는 원문을 유지합니다.

목록은 `created_at` 최신순으로 정렬합니다. 검색 pagination과 GitHub Search의 1,000개 제한을 처리하며, GraphQL 응답의 저장소 metadata는 실행 중 cache합니다.

## 로컬 dry run

Python 3.11 이상과 GitHub token이 필요합니다. 외부 package는 없습니다.

```bash
GITHUB_TOKEN="$(gh auth token)" python update_contributions.py --dry-run
```

`--dry-run`은 완성될 Markdown을 stdout에 출력하고 `README.md`는 수정하지 않습니다. 실제 파일을 갱신하려면 `--dry-run`을 빼고 실행합니다. token은 파일이나 Git에 저장하지 마십시오.

## 라이선스

[MIT License](LICENSE)
