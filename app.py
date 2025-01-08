import streamlit as st
import json
from typing import Optional, List, ClassVar, Iterator
from datetime import datetime
from pydantic import BaseModel, Field
from phi.agent import Agent
from phi.workflow import Workflow, RunResponse, RunEvent
from phi.storage.workflow.sqlite import SqlWorkflowStorage
from phi.model.deepseek import DeepSeekChat
from phi.utils.log import logger

class YogaBlogPost(BaseModel):
    """Structure for yoga blog posts"""
    title: str = Field(..., description="Engaging title for the blog post")
    perspective: str = Field(..., description="Soul Space perspective and philosophy")
    science: str = Field(..., description="Scientific research and findings")
    integration: str = Field(..., description="Integration of tradition and science")
    applications: List[str] = Field(..., description="Practical tips for students")
    takeaways: List[str] = Field(..., description="Key insights and learnings")
    references: List[str] = Field(..., description="Scientific references")

    class Config:
        arbitrary_types_allowed = True

class YogaBlogGenerator(Workflow):
    """Workflow for generating yoga blog posts"""
    description: str = "Generate scientifically-backed yoga content"
    
    writer: ClassVar[Agent] = Agent(
        model=DeepSeekChat(api_key='sk-ada27ff0f9ec45d7adf152ceb9c18da7'),
        description="Soul Space's wellness researcher creating scientifically-backed yoga content.",
        instructions=[
            "Create engaging 1000+ word content that balances scientific accuracy with accessibility",
            "Include peer-reviewed research citations",
            "Structure with clear sections using markdown",
            "Add practical tips for Soul Space students",
            "End with key takeaways and references",
            """Use this exact structure:
            ## [Title]
            ### The Soul Space Perspective
            [Content]
            ### Understanding the Science
            [Content]
            ### Traditional Wisdom Meets Modern Research
            [Content]
            ### Practical Applications
            - [Tips]
            ### Key Takeaways
            - [Points]
            ### Scientific References
            1. [References]"""
        ],
        markdown=True
    )

    def get_cached_blog_post(self, topic: str) -> Optional[str]:
        """Check if blog post exists in cache"""
        logger.info("Checking cache for existing blog post")
        return self.session_state.get("yoga_blogs", {}).get(topic)

    def add_blog_post_to_cache(self, topic: str, blog_post: Optional[str]):
        """Save blog post to cache"""
        logger.info(f"Caching blog post for: {topic}")
        self.session_state.setdefault("yoga_blogs", {})
        self.session_state["yoga_blogs"][topic] = blog_post

    def parse_response(self, content: str) -> YogaBlogPost:
        """Parse the response into sections"""
        sections = {
            'title': '',
            'perspective': '',
            'science': '',
            'integration': '',
            'applications': [],
            'takeaways': [],
            'references': []
        }
        current_section = None
        current_text = []
        
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('## '):
                sections['title'] = line.replace('## ', '')
            elif line.startswith('### The Soul Space Perspective'):
                if current_section and current_text:
                    sections[current_section] = '\n'.join(current_text)
                current_section = 'perspective'
                current_text = []
            elif line.startswith('### Understanding the Science'):
                if current_section and current_text:
                    sections[current_section] = '\n'.join(current_text)
                current_section = 'science'
                current_text = []
            elif line.startswith('### Traditional Wisdom'):
                if current_section and current_text:
                    sections[current_section] = '\n'.join(current_text)
                current_section = 'integration'
                current_text = []
            elif line.startswith('### Practical Applications'):
                if current_section and current_text:
                    sections[current_section] = '\n'.join(current_text)
                current_section = 'applications'
                current_text = []
            elif line.startswith('### Key Takeaways'):
                if current_section == 'applications':
                    sections['applications'] = [t.strip('- ') for t in current_text if t.strip('- ')]
                current_section = 'takeaways'
                current_text = []
            elif line.startswith('### Scientific References'):
                if current_section == 'takeaways':
                    sections['takeaways'] = [t.strip('- ') for t in current_text if t.strip('- ')]
                current_section = 'references'
                current_text = []
            elif not line.startswith('Namaste,'):
                if current_section in ['applications', 'takeaways', 'references']:
                    if line.startswith('- ') or line.startswith('* ') or line[0].isdigit():
                        current_text.append(line.lstrip('- *0123456789. '))
                else:
                    current_text.append(line)

        # Handle the last section
        if current_section == 'references' and current_text:
            sections['references'] = [t for t in current_text if t]

        # Ensure we have at least empty lists/strings for all fields
        sections = {k: v if v else ([] if k in ['applications', 'takeaways', 'references'] else '') 
                   for k, v in sections.items()}

        return YogaBlogPost(**sections)

    def format_blog_post(self, blog: YogaBlogPost) -> str:
        """Format blog post in Soul Space style"""
        return f"""## {blog.title}

### The Soul Space Perspective
{blog.perspective}

### Understanding the Science
{blog.science}

### Traditional Wisdom Meets Modern Research
{blog.integration}

### Practical Applications
{chr(10).join(f"- {tip}" for tip in blog.applications)}

### Key Takeaways
{chr(10).join(f"- {takeaway}" for takeaway in blog.takeaways)}

### Scientific References
{chr(10).join(f"{i+1}. {ref}" for i, ref in enumerate(blog.references))}

Namaste,
Jen Patel
Founder, Soul Space"""

    def run(self, topic: str, use_cache: bool = True) -> Iterator[RunResponse]:
        """Execute the blog post generation workflow"""
        logger.info(f"Generating yoga blog post about: {topic}")

        if use_cache:
            cached_post = self.get_cached_blog_post(topic)
            if cached_post:
                logger.info("Using cached blog post")
                yield RunResponse(
                    run_id=self.run_id,
                    event=RunEvent.workflow_completed,
                    content=cached_post
                )
                return

        prompt = f"""Write a comprehensive blog post about {topic}.
        Focus on both scientific evidence and yogic wisdom.
        Include recent research and practical applications.
        Follow the exact structure provided in the instructions."""

        try:
            response = self.writer.run(prompt)
            if response and response.content:
                blog_post = self.parse_response(response.content)
                formatted_post = self.format_blog_post(blog_post)
                self.add_blog_post_to_cache(topic, formatted_post)
                
                yield RunResponse(
                    run_id=self.run_id,
                    event=RunEvent.workflow_completed,
                    content=formatted_post
                )
            else:
                yield RunResponse(
                    run_id=self.run_id,
                    event=RunEvent.workflow_completed,
                    content=f"Failed to generate blog post about: {topic}"
                )
        except Exception as e:
            logger.error(f"Error generating blog post: {str(e)}")
            yield RunResponse(
                run_id=self.run_id,
                event=RunEvent.workflow_completed,
                content=f"Error: {str(e)}"
            )

def generate_blog_post(topic: str) -> str:
    """Generate a blog post using the workflow"""
    url_safe_topic = topic.lower().replace(" ", "-")
    
    blog_generator = YogaBlogGenerator(
        session_id=f"yoga-blog-{url_safe_topic}",
        storage=SqlWorkflowStorage(
            table_name="yoga_blog_workflows",
            db_file="tmp/workflows.db",
        ),
    )

    try:
        for response in blog_generator.run(topic=topic, use_cache=True):
            return response.content
    except Exception as e:
        return f"Error generating blog post: {str(e)}"

def main():
    st.set_page_config(
        page_title="Soul Space Blog Generator",
        page_icon="🧘‍♀️",
        layout="wide"
    )

    st.title("🧘‍♀️ Soul Space Blog Generator")
    st.markdown("Generate scientifically-backed yoga and wellness content")

    # Sidebar for settings and info
    with st.sidebar:
        st.header("About")
        st.markdown("""
        Soul Space Blog Generator creates comprehensive blog posts that blend:
        - Scientific research
        - Traditional yoga wisdom
        - Practical applications
        - Evidence-based insights
        """)
        
        st.header("Settings")
        use_cache = st.checkbox("Use cached posts", value=True)

    # Main content area
    col1, col2 = st.columns([2, 3])

    with col1:
        st.subheader("Generate New Post")
        topic = st.text_input(
            "Enter blog topic",
            placeholder="e.g., Benefits of Pranayama for Stress Management",
            key="topic_input"
        )
        
        generate_button = st.button("Generate Blog Post", type="primary")
        
        if generate_button and topic:
            with st.spinner("Generating your blog post..."):
                blog_content = generate_blog_post(topic)
                st.session_state.current_blog = blog_content

    with col2:
        st.subheader("Generated Content")
        if "current_blog" in st.session_state:
            st.markdown(st.session_state.current_blog)
            
            # Export options
            st.download_button(
                label="Download as Markdown",
                data=st.session_state.current_blog,
                file_name=f"blog_post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown"
            )

    # Footer
    st.markdown("---")
    st.markdown(
        "Created by Soul Space | Blending Ancient Wisdom with Modern Science",
        help="Powered by AI technology"
    )

if __name__ == "__main__":
    main() 
